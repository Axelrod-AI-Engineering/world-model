# China Construction Bank: business construction

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
- [Conversion to the new method forms (Oct 18, second round)](#conversion-to-the-new-method-forms-oct-18-second-round)
- [What the method could not express for this bank](#what-the-method-could-not-express-for-this-bank)
<!-- /toc -->

The fourth build of the method, and the second bank after [JPMorgan](jpmorgan.md): a Chinese state bank reporting
under IFRS (and CAS) in RMB, whose economics are a balance sheet that reprices off administered benchmarks (the loan
prime rate for loans, posted deposit rates for deposits), a large government bond book, a mortgage-heavy loan book
exposed to the property market, fees under regulatory caps, and capital and payout set with the state as controlling
shareholder.

## Gap register

Written before the model was changed. "Internal" is the loaded sally_demo graph and its YAML; "export" is the v4.1.4
pack the reviewer inspected (036, state 432). China Construction Bank was not one of the reviewer's worked companies;
in the inspected export it appears as a company, one cluster membership and seven relationships (s27–s31, s58, s61)
plus the kind-default net profit → share price link. Categories: **MC** missing construction, **CAL** missing
calibration, **MAP** incorrect mapping, **EXP** export omission, **RET** retrieval omission. Outcomes are in the
[completion report](#completion-report).

| # | Gap (missing or incorrect structure) | Present now (internal / export) | Add or correct | Evidence or input needed | Conclusions affected | Test that shows it done | Cat. |
|---|---|---|---|---|---|---|---|
| G01 | No business composition: the pack jumps from the LPR to the margin to net profit, from property sales to the NPL ratio to net profit, and from credit growth straight to net profit | Internal: three values (`net_interest_margin`, `npl_ratio`, `operating_profit`), links s27–s31, s58; no compositions. Export: the same relations | Operating income by line (driven), the P&L bridge to profit before tax and net profit, NII by earning asset and funding source, fees by product, credit impairment, loans by type, interest-earning assets | Company income statement and notes (IFRS lines) | Any revenue or earnings conclusion; "an LPR cut is bad for the bank" | `test_required_compositions_exist`, `test_composition_parts_have_fixed_weight_accounting_links`, `test_priors_reconcile_within_half_a_percent` | MC |
| G02 | `china_construction_bank.operating_profit` holds net profit (its name says so) under an operating-profit id; the kind-default link to the share price is labelled by operating profit; NIM and NPL ratio carry no definition | Internal: values without features. Export: metric named by the id suffix (`operating_profit`) | `features.view/basis/metric` (metric `net_profit`) on the three values; ids kept for Sally's expected paths | IFRS net profit definition (group, incl. minority interests) | Reading the bank's earnings as an operating line; mixing NIM definitions | `test_values_name_their_basis` | MAP |
| G03 | s27 (LPR → NIM) and s29 (NIM → net profit) are unscoped statistical records; s58 (CGB 10Y → NIM) has no scope | Internal: calibrated, no transition | Keep ids and sizes; add transitions naming them reduced forms of `ccb.path.lpr_nii` and `ccb.path.cgb_yields`, magnitude "assumption", with the inputs that would recalibrate them | NII sensitivity to an LPR cut (repricing gap by tenor) | Size of any LPR-driven margin change | `test_existing_records_keep_their_sizes_and_are_scoped`, `test_reduced_forms_are_never_steps_of_their_structural_paths` | MAP / CAL |
| G04 | NII drivers absent: loans reprice off the 1-year LPR (corporate) and the 5-year LPR (mortgages, annual reset); deposits reprice only through posted-rate cuts and time-deposit maturities; NIM is a ratio | Internal: none; no 5-year LPR in the world | `ccb.path.lpr_nii` (parallel branches of one LPR move), `pboc.loan_prime_rate_5y`, operating states for yields, deposit cost, balances, NIM as NII over earning assets | Repricing schedule by tenor, deposit maturity profile, loan pricing relative to the LPR | Whether and when an LPR cut compresses NII; deposit-rate catch-up | `test_shared_driver_responses_are_parallel_branches` | MC |
| G05 | Deposit repricing and migration: posted-rate cuts, time-deposit share, migration to wealth products (lower deposit growth, higher agency fees), mortgage prepayment as deposit yields fall | Internal: none | `ccb.path.deposit_repricing` with its counter-paths (agency fees up, prepayment) | Deposit cost by type, migration volumes | "Deposit cuts fully offset LPR cuts" | `test_deposit_repricing_has_its_counter_paths` | MC |
| G06 | Bond book: falling CGB yields lower the reinvestment yield as bonds roll, lift FVOCI reserves (in CET1) and realize trading gains; reinvestment below the book yield | Internal: s58 only | `ccb.path.cgb_yields`, `ccb.path.securities_reinvestment`; s58 scoped as the reduced form | Book yield, maturities, new-purchase yields, FVOCI duration | "Lower yields hurt NIM" vs "lift gains and capital" | `test_falling_yields_reach_income_gains_and_capital_separately` | MC / CAL |
| G07 | Property and asset quality: mortgage and developer NPLs into the NPL ratio, IFRS 9 allowance build and write-offs into credit impairment; the provision-coverage buffer as a counter-path; mortgage volume and prepayment | Internal: s28, s30 (property → NPL ratio → net profit), unscoped | `ccb.path.property_credit`; s28, s30 scoped | Mortgage and developer NPL ratios, ECL scenario weights, coverage floor, prepayment rate | Any property-cycle conclusion | `test_property_reaches_impairment_through_npls_and_the_outlook` | MC / CAL |
| G08 | Policy direction: a fiscally funded mortgage interest subsidy (bank-friendly: not priced by the bank) and state capital support | Internal: none | `china_economy.mortgage_interest_subsidy`, `ccb.path.mortgage_subsidy`; `china_construction_bank.capital_injection`, `ccb.path.state_capital` | Eligible volume; the bank's share of the injection | Policy support read as an NIM cut | `test_policy_support_is_represented` | MC |
| G09 | Loan growth by type (policy-directed corporate lending against a contracting retail book), its yield cost and its RWA cost; s31 unscoped | Internal: s31 only | `ccb.path.credit_growth`, `ccb.comp.loans_by_type`; s31 scoped | Loan growth by type, risk weights | "Loan growth lifts profit" | `test_required_paths_exist` | MC |
| G10 | Fees: wealth agency fees on capital markets and deposit migration, regulatory fee caps; card and settlement fees on activity | Internal: none | `ccb.comp.fees`, `ccb.path.wealth_fees`; activity fee links | Fee income by product | Fee recovery conclusions | `test_required_paths_exist` | MC |
| G11 | Capital and payout: CET1 capital as a stock fed by profit, dividends, FVOCI marks and injections; RWA; requirement (systemic surcharge, TLAC); a payout ratio set with the state shareholder | Internal: none | Capital values, non-additive `ccb.comp.capital_sources_uses`, `ccb.path.capital_payout`, `ccb.path.capital_requirements` | CET1 ratio and capital, payout policy, requirement | Dividend capacity; growth capacity | `test_capital_is_a_stock_with_flows_not_an_additive_view` | MC |
| G12 | Reporting segments (Corporate Finance, Personal Finance, Treasury and Asset Management, Others) | Internal: none | `ccb.comp.operating_income_by_segment`, `ccb.comp.pbt_by_segment` (Others as residual, incl. inter-segment items), undriven | Segment results | Segment mix | `test_segment_views_are_separate_from_the_driven_view` | MC |
| G13 | Operating expenses and cost-to-income | Internal: none | Held as an undriven part of the P&L bridge | A driver for staff and administrative costs | Operating leverage | listed as not built | MC |
| G14 | Adding a CCB NII value would create a calibrated kind-default NII → share price link (0.5) beside net profit → share price: double counting with no evidence | Taxonomy default links (objects.yaml) | Write the NII → share price link out, uncalibrated, so the default does not apply | none | Share-price forecasts | `test_no_new_statistical_link_on_nii` | MAP |
| G15 | New objects absent from the export | Export: none | Transitions in relationship properties, `financial_bridge`, `business_construction` paths | none | Downstream agent context | `test_new_objects_reach_the_export` | EXP |
| G16 | New node ids not retrievable | Internal API: none | `/v1/world-models/sally_demo/graph`, `…/entities/china_construction_bank/construction` and its traces | none | Agent retrieval | `test_new_objects_reach_the_api` | RET |
| G17 | No company workbook was supplied: line, segment, balance-sheet and capital levels have no dated baselines beyond a summary statement | Supplied material: six PDFs (five broker or vendor notes, one algorithmic summary) | Bind what the PDFs hold; report the rest as not disclosed | A company model workbook or the annual report | Baseline reconciliation of every view | reconciliation at the baselines (completion report) | CAL |
| G18 | Overseas operations and FX (USD funding, Hong Kong and overseas branches) | Internal: none | Not built (a small share of the bank; nothing in the supplied material) | Overseas assets and income | FX translation | listed as not built | MC |

## Audit before modifying

| Requirement or object | Class | Controlling object | Action |
|---|---|---|---|
| Identity, aliases, kind, cluster membership, share-price kind default and its net profit → share price default link (`china_construction_bank`) | Already owned | entities.yaml `china_construction_bank`, taxonomy objects.yaml | untouched |
| s27, s28, s29, s30, s31, s58 (statistical records on the bank's values; Sally's S-T4 thesis reads them) | Already owned → Modify lightly | interactions.yaml | ids, sizes and kernels kept; transitions added (scope, reduced form, evidence, unresolved inputs with search status) |
| s61 (China equities → share price), s56, s57, s02–s04, s77, s78 (shared China macro links) | Do not touch | interactions.yaml | untouched; the bank's paths start below them and use s56 and s03 as given |
| `net_interest_margin`, `npl_ratio`, `operating_profit` definitions | Modify lightly | entities.yaml | `features.view/basis/metric` added (`operating_profit` carries metric `net_profit`); ids and priors kept |
| Compositions, operating states, connected paths, financial mappings, a 5-year LPR, a fiscal mortgage subsidy, bindings | Missing | construction/china_construction_bank.yaml; local sources, citations, baselines | built |
| The taxonomy's default NII → share price link (applies to any company with an NII value) | Do not touch (shared taxonomy) | taxonomy objects.yaml | suppressed for this bank by writing the link out, uncalibrated (G14) |
| Other banks' objects (JPMorgan, Citigroup, UniCredit, AIB) | Do not touch | construction/jpmorgan.yaml, entities.yaml | untouched; JPMorgan's US macro values are not needed here |

## Definitions and bases

- **Basis**: IFRS, group, RMB bn (`CNY bn/yr` for flows, `CNY bn` for balances, `pct` for rates and ratios). The
  A-share CAS accounts agree with IFRS at group net profit; no CAS-to-IFRS bridge is represented.
- **Net profit** is the existing value `china_construction_bank.operating_profit` (group net profit including minority
  interests; metric `net_profit`). There is no operating-profit line in a Chinese bank's income statement; the id is
  kept because Sally's expected paths read it.
- **Operating income** (`operating_income`) = net interest income + net fee and commission income + other operating
  income (trading, investment gains, insurance result and other; the residual). **The segment view**
  (`ccb.comp.operating_income_by_segment`): Corporate Finance + Personal Finance + Treasury and Asset Management +
  Others (residual, incl. inter-segment items). Both total operating income; they are never added to each other, and
  only the line view is driven. The same holds for profit before tax (`ccb.comp.pretax` driven,
  `ccb.comp.pbt_by_segment` reported).
- **NIM** is NII over average interest-earning assets (`ccb.comp.earning_assets`): a ratio, held as two signed links
  tagged `identity: ratio`. It is never calibrated beside s29 (NIM → net profit), which would count NII twice.
- **Costs and charges are negative values** (operating expenses, credit impairment, write-offs, allowance build,
  interest expense, tax), so every part adds to its total with a positive weight.
- **Credit**: loan impairment = net write-offs + allowance build (the IFRS 9 allowance roll-forward). The allowance
  build responds to staging (NPL migration) and to the forward-looking outlook (property), and the provision-coverage
  buffer lets the bank smooth it; write-offs follow realized losses later.
- **Capital**: CET1 capital is a stock fed by net profit, dividends (out), the FVOCI reserve (OCI counts in core tier 1
  under China's capital rules) and state injections; the CET1 ratio is capital over RWA. Neither is an additive view.
- **Rates**: corporate loans price off the 1-year LPR (`pboc.loan_prime_rate`), mortgages off the 5-year LPR
  (`pboc.loan_prime_rate_5y`, new), deposits off the bank's posted rates (`deposit_list_rate`), which follow LPR cuts by
  administrative coordination, not by a market beta.
- **Conversion tags** (until identity, stock-flow, matrix and state-dependent link forms exist): each such step is an
  uncalibrated link whose `note` read `identity: ...`, `stock-flow: ...`, `matrix: ...` or `state: ...` (33
  links); 23 are now identities, stock-flows or state blocks, and 10 say in their note why not (see the conversion).
- Fiscal year = calendar year. Source ids: `ccb.v1` algorithmic summary report (FY2023–25 summary financials, segment
  list); `ccb.r1`, `ccb.r2`, `ccb.r3` broker sector notes on the China banks (policy package, mortgage subsidy, credit
  data); `ccb.r4` vendor sector research (margins, deposits, fees, asset quality, capital, by bank where the chart text
  survives); `ccb.r5` broker credit research (a Tier 2 bond's call); `ccb.pub` public business, accounting and
  regulatory knowledge. Each resolves locally (`sources.json`; passages in `citations.json`). No company workbook or
  company report was supplied.

## Readable view

Generated by `uv run python scripts/construction/check.py sally_demo --entities china_construction_bank` from the
loaded model (the same objects the API serves at `/v1/world-models/sally_demo/entities/china_construction_bank/construction`). A `?` marks a
step whose size is unknown (uncalibrated). Levels are left out here; the local copy has the objects as JSON.

102 links touch its values: 68 calibrated, 34 uncalibrated (represented, size unknown), 34 accounting, 21 identity, 5 stock-flow; 3 state-dependent; 100 carry a transition.

### Business composition

#### capital: CET1 capital roll-forward: profit in, dividends out, FVOCI marks, state injections (not an additive partition: flows into a stock) (CNY bn)

| Part | Value |
|---|---|
| CCB net profit | `china_construction_bank.operating_profit` |
| CCB ordinary dividends | `china_construction_bank.dividends` |
| CCB FVOCI fair value reserve | `china_construction_bank.fvoci_reserve` |
| CCB state capital injection | `china_construction_bank.capital_injection` |
| **Total: CCB CET1 capital** | `china_construction_bank.cet1_capital` |

A non-additive view: its parts overlap.
Capital accumulates: next period's CET1 is this period's plus net profit less dividends plus the change in the FVOCI reserve plus any injection, less deductions. Profit, dividends and injections accumulate through the stock-flow ccb.sf.cet1_capital; the FVOCI reserve is a stock whose change enters CET1, held as a signed link (ccb-c-fvoci-cet1).

#### credit: credit impairment losses by asset (negative values) (CNY bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| CCB loan impairment losses | `china_construction_bank.loan_impairment` |
| Residual: CCB impairment on other assets | `china_construction_bank.other_impairment` |
| **Total: CCB credit impairment losses** | `china_construction_bank.credit_impairment` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Loans are most of the charge.

#### investment assets: interest-earning assets by type (CNY bn, average balance for the fiscal year)

| Part | Value |
|---|---|
| CCB loans and advances | `china_construction_bank.loans` |
| CCB financial investments | `china_construction_bank.financial_investments` |
| Residual: CCB other earning assets | `china_construction_bank.other_earning_assets` |
| **Total: CCB interest-earning assets** | `china_construction_bank.earning_assets` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
The NIM denominator. The residual is central bank reserves and interbank assets.

#### product: net fee and commission income by product (CNY bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| CCB agency service fees | `china_construction_bank.agency_fees` |
| CCB bank card fees | `china_construction_bank.card_fees` |
| CCB settlement and clearing fees | `china_construction_bank.settlement_fees` |
| Residual: CCB other fees | `china_construction_bank.other_fees` |
| **Total: CCB net fee and commission income** | `china_construction_bank.net_fee_income` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Agency (wealth distribution) fees follow capital markets and deposit migration and sit under regulatory fee-rate caps; the residual holds fee expense.

#### liabilities: interest expense by funding source (negative values) (CNY bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| CCB interest expense on deposits | `china_construction_bank.deposit_interest_expense` |
| Residual: CCB other interest expense | `china_construction_bank.other_interest_expense` |
| **Total: CCB interest expense** | `china_construction_bank.interest_expense` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Deposits reprice through posted-rate cuts and time-deposit maturities; the residual reprices at money-market rates.

#### investment assets: interest income by earning asset (CNY bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| CCB interest income on loans | `china_construction_bank.loan_interest_income` |
| CCB interest income on financial investments | `china_construction_bank.investment_interest_income` |
| Residual: CCB other interest income | `china_construction_bank.other_interest_income` |
| **Total: CCB interest income** | `china_construction_bank.interest_income` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Loans reprice off the LPR; the bond book reprices only as it rolls; the residual is central bank and interbank income.

#### credit: loan impairment: net write-offs plus allowance build (allowance roll-forward) (CNY bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| CCB net loan write-offs | `china_construction_bank.net_write_offs` |
| CCB loan allowance build | `china_construction_bank.allowance_build` |
| **Total: CCB loan impairment losses** | `china_construction_bank.loan_impairment` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
The allowance roll-forward (charge = write-offs net of recoveries + change in allowance; other movements negligible). Write-offs follow realized losses; the build follows staging and the forward-looking outlook.

#### investment assets: interest income on loans by portfolio (CNY bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| CCB interest income on corporate loans | `china_construction_bank.corporate_loan_income` |
| CCB interest income on mortgages | `china_construction_bank.mortgage_income` |
| Residual: CCB interest income on other loans | `china_construction_bank.other_loan_income` |
| **Total: CCB interest income on loans** | `china_construction_bank.loan_interest_income` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Each named part is a product identity (balance x yield); the residual holds the portfolios without a yield value.

#### product: gross loans and advances by type (CNY bn, average balance for the fiscal year)

| Part | Value |
|---|---|
| CCB corporate loans | `china_construction_bank.corporate_loans` |
| CCB residential mortgages | `china_construction_bank.mortgages` |
| CCB other personal loans | `china_construction_bank.other_personal_loans` |
| Residual: CCB discounted bills and other loans | `china_construction_bank.other_loans` |
| **Total: CCB loans and advances** | `china_construction_bank.loans` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Mortgages are a large share of loans at this bank (high among peers). The residual holds discounted bills, overseas and other loans.

#### reporting segments: net profit: profit before tax less income tax (CNY bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| CCB profit before tax | `china_construction_bank.profit_before_tax` |
| CCB income tax | `china_construction_bank.income_tax` |
| **Total: CCB net profit** | `china_construction_bank.operating_profit` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An identity. Net profit is the group figure incl. minority interests (the existing value china_construction_bank.operating_profit).

#### investment assets: net interest income: interest income less interest expense (CNY bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| CCB interest income | `china_construction_bank.interest_income` |
| CCB interest expense | `china_construction_bank.interest_expense` |
| **Total: CCB net interest income** | `china_construction_bank.net_interest_income` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An identity: interest expense is held negative.

#### product: operating income by line: net interest income, net fee and commission income and other operating income (CNY bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| CCB net interest income | `china_construction_bank.net_interest_income` |
| CCB net fee and commission income | `china_construction_bank.net_fee_income` |
| Residual: CCB other operating income | `china_construction_bank.other_operating_income` |
| **Total: CCB operating income** | `china_construction_bank.operating_income` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
The driven view: rates and balances enter through NII, capital markets and activity through fees, bond yields through other operating income (gains). Not the segment view (ccb.comp.operating_income_by_segment): never added to it.

#### reporting segments: operating income by reporting segment (CNY bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| CCB Corporate Finance operating income | `china_construction_bank.corporate_finance_income` |
| CCB Personal Finance operating income | `china_construction_bank.personal_finance_income` |
| CCB Treasury and Asset Management operating income | `china_construction_bank.treasury_income` |
| Residual: CCB Others segment operating income | `china_construction_bank.other_segment_income` |
| **Total: CCB operating income** | `china_construction_bank.operating_income` |

A reconciling view: its parts are observed and reconciled against the total but carry nothing into it, so it can be imported alongside the driving view without counting a change twice.
Reconciling view (drives: false): reported and reconciled, never linked into the total. The drivers act on lines (NII, fees) that cut across segments; the line view drives. Others is the residual and holds the inter-segment items.

#### reporting segments: profit before tax by reporting segment (CNY bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| CCB Corporate Finance profit before tax | `china_construction_bank.corporate_finance_pbt` |
| CCB Personal Finance profit before tax | `china_construction_bank.personal_finance_pbt` |
| CCB Treasury and Asset Management profit before tax | `china_construction_bank.treasury_pbt` |
| Residual: CCB Others segment profit before tax | `china_construction_bank.other_segment_pbt` |
| **Total: CCB profit before tax** | `china_construction_bank.profit_before_tax` |

A reconciling view: its parts are observed and reconciled against the total but carry nothing into it, so it can be imported alongside the driving view without counting a change twice.
Reconciling view (drives: false): reported and reconciled, never linked into the total; the P&L bridge (ccb.comp.pretax) drives. Others is the residual.

#### reporting segments: profit before tax: operating income less operating expenses less credit impairment (CNY bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| CCB operating income | `china_construction_bank.operating_income` |
| CCB operating expenses | `china_construction_bank.operating_expenses` |
| CCB credit impairment losses | `china_construction_bank.credit_impairment` |
| Residual: CCB other pre-tax items | `china_construction_bank.other_pretax_items` |
| **Total: CCB profit before tax** | `china_construction_bank.profit_before_tax` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Costs and charges are negative values. The residual holds insurance service expenses, other operating expenses and share of associates.

### Identities

Each weight is derived from the values' levels and scales at construction (sd of the target per sd of the term), never estimated.

| Identity | Formula | Terms (weight, sd/sd) | Unit check |
|---|---|---|---|
| `ccb.id.cet1_ratio` (ratio) | CCB CET1 ratio = 100 x CCB CET1 capital / CCB risk-weighted assets | CCB CET1 capital (numerator, +0.952); CCB risk-weighted assets (denominator, -1.400) | % = CNY bn / CNY bn x 100 |
| `ccb.id.corporate_loan_income` (product) | CCB interest income on corporate loans = 0.01 x CCB corporate loans x CCB corporate loan yield | CCB corporate loans (factor, +0.800); CCB corporate loan yield (factor, +0.556) | CNY bn/yr = CNY bn x % x 0.01 |
| `ccb.id.deposit_interest` (product) | CCB interest expense on deposits = -0.01 x CCB customer deposits x CCB deposit cost | CCB customer deposits (factor, -0.780); CCB deposit cost (factor, -1.300) | CNY bn/yr (negative) = CNY bn x % x -0.01 |
| `ccb.id.dividends` (product) | CCB ordinary dividends = 0.01 x CCB dividend payout ratio x CCB net profit | CCB dividend payout ratio (factor, +0.628); CCB net profit (factor, +0.502) | CNY bn/yr = % x CNY bn/yr x 0.01 |
| `ccb.id.investment_interest` (product) | CCB interest income on financial investments = 0.01 x CCB financial investments x CCB financial investment yield | CCB financial investments (factor, +1.000); CCB financial investment yield (factor, +0.600) | CNY bn/yr = CNY bn x % x 0.01 |
| `ccb.id.mortgage_income` (product) | CCB interest income on mortgages = 0.01 x CCB residential mortgages x CCB mortgage yield | CCB residential mortgages (factor, +0.750); CCB mortgage yield (factor, +0.735) | CNY bn/yr = CNY bn x % x 0.01 |
| `ccb.id.nim` (ratio) | CCB net interest margin = 100 x CCB net interest income / CCB interest-earning assets | CCB net interest income (numerator, +1.136); CCB interest-earning assets (denominator, -0.852) | % = CNY bn/yr / CNY bn x 100 |
| `ccb.id.nonperforming_loans` (product) | CCB non-performing loans = 0.01 x CCB non-performing loan ratio x CCB loans and advances | CCB non-performing loan ratio (factor, +0.752); CCB loans and advances (factor, +0.600) | CNY bn = % x CNY bn x 0.01 |
| `ccb.id.npl_ratio` (weighted_average) | CCB non-performing loan ratio = 0.2 x CCB mortgage NPL ratio + 0.04 x CCB developer loan NPL ratio + 0.76 x CCB NPL ratio on other loans | CCB mortgage NPL ratio (weight 0.2, +0.320); CCB developer loan NPL ratio (weight 0.04, +0.320); CCB NPL ratio on other loans (weight 0.76, +0.760) | % = sum of loan shares x % |
| `ccb.id.provision_coverage` (ratio) | CCB provision coverage ratio = 100 x CCB loan loss reserve / CCB non-performing loans | CCB loan loss reserve (numerator, +1.157); CCB non-performing loans (denominator, -1.150) | % = CNY bn / CNY bn x 100 |

### Stocks and flows

A flow held one sd above its level adds its weight to the stock every period: the stock accumulates it.

| Stock-flow | Roll-forward | Flows (weight per period, sd/sd) |
|---|---|---|
| `ccb.sf.cet1_capital` | CCB CET1 capital (closing) = CCB CET1 capital (opening) + CCB net profit + CCB state capital injection - CCB ordinary dividends, per 365 days | CCB net profit (inflow, +0.223); CCB state capital injection (inflow, +0.667); CCB ordinary dividends (outflow, -0.133) |
| `ccb.sf.loan_loss_reserve` | CCB loan loss reserve (closing) = CCB loan loss reserve (opening) - CCB loan allowance build, per 365 days | CCB loan allowance build (outflow, -0.375) |
| `ccb.sf.mortgages` | CCB residential mortgages (closing) = CCB residential mortgages (opening) - CCB mortgage prepayments, per 365 days; the stock is a period average | CCB mortgage prepayments (outflow, -0.962) |

### Operating and financial paths

#### CCB profit to capital and dividends

**Trigger:** net profit changes. **Endpoint:** CCB CET1 ratio.

CCB net profit → [retain] CCB CET1 capital → [distribute] CCB ordinary dividends → CCB CET1 capital → CCB CET1 ratio

Profit is retained in CET1 or paid out at the payout ratio; dividends leave capital; the ratio is capital over RWA.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [retain] `ccb-c-np-cet1` | Net profit adds to retained earnings and so to CET1 capital (a flow into a stock: next period's capital is this period's plus profit less dividends) (group) | accumulation over the period; observable: CET1 capital roll-forward | onset period end; build cumulative; persists permanent; recognized capital reporting each quarter | documented / documented / model / documented | dividends above profit | CET1 capital | +0.22 sd/sd (stock-flow, accumulates per 365 days) |
| 2 [distribute] `ccb-c-np-dividends` | Dividends are the payout ratio times net profit attributable to shareholders; the large state banks have long held the payout near 30%, paid in interim and final instalments (board and the state shareholder) | payout ratio held; observable: dividend per share and payout ratio | onset declared with interim and annual results; build none; persists the year; recognized equity when declared | documented / documented / model / documented | a payout change (ccb-c-payout-dividends) | ordinary dividends | +0.50 sd/sd (identity) |
| 3 `ccb-c-dividends-cet1` | Declared dividends are deducted from CET1 capital (group) | dividends declared; observable: CET1 capital roll-forward | onset when declared; build none; persists permanent; recognized capital reporting each quarter | documented / documented / model / documented | none | CET1 capital | -0.13 sd/sd (stock-flow, accumulates per 365 days) |
| 4 `ccb-c-cet1cap-ratio` | The CET1 ratio is CET1 capital over risk-weighted assets (CCB (capital management)) | RWA unchanged; observable: CET1 ratio, quarterly | onset same reporting date; build none; persists identity; recognized capital reporting each quarter | documented / documented / model / documented | RWA growth | CET1 ratio | +0.95 sd/sd (identity) |

Unresolved inputs: CET1 capital and ratio (found connected); dividend payout ratio policy (found connected).

#### CCB capital requirements and payout

**Trigger:** capital requirements rise (systemic surcharge bucket, TLAC). **Endpoint:** CCB CET1 ratio.

CCB CET1 requirement → CCB dividend payout ratio? → CCB ordinary dividends → CCB CET1 capital → CCB CET1 ratio  (? marks a step whose size is unknown)

A tighter requirement holds the payout back (when the surplus is thin), keeping more profit in capital.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `ccb-c-req-payout` | Higher requirements (a systemic surcharge bucket, TLAC) leave less surplus capital, so the bank holds the payout rather than raising it; with a wide surplus the requirement does not bind (board, regulator and the state shareholder) | the surplus over the requirement narrows; observable: CET1 ratio against the requirement; payout ratio | onset next dividend decision; build none; persists while the requirement holds; recognized dividends when declared | broker / broker / unknown / broker | a wide surplus; state preference for steady dividends | dividend payout ratio | unknown; acts only while CCB CET1 ratio is below 10.5 |
| 2 `ccb-c-payout-dividends` | A higher payout ratio pays more of the same profit as dividends (board and the state shareholder) | profit unchanged; observable: payout ratio | onset declared with results; build none; persists the year; recognized equity when declared | documented / documented / model / documented | a capital need (ccb-c-req-payout) | ordinary dividends | +0.63 sd/sd (identity) |
| 3 `ccb-c-dividends-cet1` | Declared dividends are deducted from CET1 capital (group) | dividends declared; observable: CET1 capital roll-forward | onset when declared; build none; persists permanent; recognized capital reporting each quarter | documented / documented / model / documented | none | CET1 capital | -0.13 sd/sd (stock-flow, accumulates per 365 days) |
| 4 `ccb-c-cet1cap-ratio` | The CET1 ratio is CET1 capital over risk-weighted assets (CCB (capital management)) | RWA unchanged; observable: CET1 ratio, quarterly | onset same reporting date; build none; persists identity; recognized capital reporting each quarter | documented / documented / model / documented | RWA growth | CET1 ratio | +0.95 sd/sd (identity) |

Unresolved inputs: CET1 capital and ratio (found connected); CET1 requirement incl. systemic surcharge and TLAC (found proxy); dividend payout ratio policy (found connected).

#### CCB government bond yields to NII, gains and capital

**Trigger:** Chinese government bond yields fall. **Endpoint:** CCB CET1 ratio.

CGB 10Y yield → [yield] CCB bond new-purchase yield? → [marks] CCB FVOCI fair value reserve? → [trading] CCB other operating income? → CCB financial investment yield? → CCB interest income on financial investments → CCB interest income → CCB net interest income → CCB operating income → CCB operating income → CCB profit before tax → CCB net profit → CCB CET1 capital? → CCB CET1 capital → CCB CET1 ratio  (? marks a step whose size is unknown)

One move, three responses: new purchases earn less (the book yield drifts down as bonds roll), FVOCI bonds mark up into OCI and CET1 (not profit), and trading and disposal gains offset part of the margin loss for a while. s58 is the reduced form (CGB 10Y to NIM) and is never added to these steps.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [yield] `ccb-c-cgb-npy` | The treasury buys government, local government and policy-bank bonds at prevailing yields, so new-purchase yields follow the curve (CCB treasury) | purchases spread across tenors near the 10-year point; observable: yield on bonds bought in the period | onset at purchase; build none; persists to maturity; recognized accrual each period | documented / inferred / unknown / unknown | a shift in tenor or issuer mix (local government bonds above the CGB curve) | bond new-purchase yield | unknown |
| 2 [marks] `ccb-c-cgb-fvoci` | Bond prices move inversely to yields: falling yields raise the fair value of bonds held at FVOCI, lifting the reserve in other comprehensive income (and so CET1), not profit (CCB treasury) | bonds classified at FVOCI; duration of that book; observable: FVOCI reserve in OCI, half-yearly | onset at once (marked each reporting date); build none; persists until maturity or sale (pull to par); recognized other comprehensive income at the reporting date | documented / documented / unknown / documented | a reclassification or sale realizes the gain in profit (ccb-c-cgb-trading) | FVOCI fair value reserve | unknown |
| 3 [trading] `ccb-c-cgb-trading` | Counter-path: falling yields create gains on bonds held for trading and on FVOCI disposals; the large state banks gain more because their bond books are larger, which offsets part of the margin squeeze (CCB treasury) | the treasury sells or marks trading bonds; yields fall rather than rise; observable: net trading gain and net gain on financial investments | onset within the quarter; build none; persists one-off: gains are not recurring; recognized profit in the period realized | broker / broker / unknown / broker | with yields near historic lows, two-way moves create mark-to-market losses; rising yields reverse the sign | other operating income | unknown |
| 4 `ccb-c-npy-invyield` | Each year's purchases replace maturing bonds, so the book yield drifts toward new-purchase yields at the pace of maturities (CCB treasury) | bonds maturing and reinvested in bonds (not held as reserves or lent); observable: book yield on financial investments, half-yearly | onset as bonds mature; build years (the book's remaining life); persists to maturity; recognized interest income each period | documented / documented / unknown / inferred | the treasury holds cash or lends instead of reinvesting | financial investment yield | unknown |
| 5 `ccb-c-invyield-invii` | Interest income on financial investments is the average balance times the book yield (CCB treasury) | bilinear: balance times yield; observable: book yield and investment interest income | onset same period; build none; persists while held; recognized interest income each period | documented / documented / model / documented | a shrinking book | interest income on financial investments | +0.60 sd/sd (identity) |
| 6 `ccb-a-ii-investment-interest-income` | CCB interest income on financial investments is one part of CCB interest income (interest income by earning asset); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | interest income | +0.21 sd/sd (accounting) |
| 7 `ccb-a-nii-interest-income` | CCB interest income is one part of CCB net interest income (net interest income: interest income less interest expense); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | net interest income | +1.62 sd/sd (accounting) |
| 8 `ccb-a-oi-net-interest-income` | CCB net interest income is one part of CCB operating income (operating income by line: net interest income, net fee and commission income and other operating income); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | operating income | +0.77 sd/sd (accounting) |
| 9 `ccb-a-oi-other-operating-income` | CCB other operating income is the residual of CCB operating income: what the named parts leave out, stated in its basis (operating income by line: net interest income, net fee and commission income and other operating income); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | operating income | +0.33 sd/sd (accounting) |
| 10 `ccb-a-pbt-operating-income` | CCB operating income is one part of CCB profit before tax (profit before tax: operating income less operating expenses less credit impairment); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | profit before tax | +1.54 sd/sd (accounting) |
| 11 `ccb-a-np-profit-before-tax` | CCB profit before tax is one part of CCB net profit (net profit: profit before tax less income tax); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | net profit | +1.46 sd/sd (accounting) |
| 12 `ccb-c-fvoci-cet1` | The FVOCI reserve is part of other comprehensive income, which China's capital rules count in core tier 1 capital (CCB (capital management)) | no prudential filter on the reserve; observable: CET1 capital roll-forward | onset reporting date; build none; persists while the bonds are held; recognized capital reporting each quarter | documented / documented / unknown / documented | a prudential filter on unrealized gains | CET1 capital | unknown |
| 13 `ccb-c-np-cet1` | Net profit adds to retained earnings and so to CET1 capital (a flow into a stock: next period's capital is this period's plus profit less dividends) (group) | accumulation over the period; observable: CET1 capital roll-forward | onset period end; build cumulative; persists permanent; recognized capital reporting each quarter | documented / documented / model / documented | dividends above profit | CET1 capital | +0.22 sd/sd (stock-flow, accumulates per 365 days) |
| 14 `ccb-c-cet1cap-ratio` | The CET1 ratio is CET1 capital over risk-weighted assets (CCB (capital management)) | RWA unchanged; observable: CET1 ratio, quarterly | onset same reporting date; build none; persists identity; recognized capital reporting each quarter | documented / documented / model / documented | RWA growth | CET1 ratio | +0.95 sd/sd (identity) |

Unresolved inputs: CET1 capital and ratio (found connected); FVOCI bond holdings and their duration (disclosed not supplied); financial investments: book yield, maturities and new-purchase yields (disclosed not supplied); net trading and investment gains (disclosed not supplied).

#### CCB credit growth to NII and capital

**Trigger:** system credit growth picks up. **Endpoint:** CCB net profit.

China total social financing growth → [corporate] CCB corporate loans? → [retail] CCB other personal loans? → CCB corporate loan yield? → CCB interest income on corporate loans → CCB interest income on other loans? → CCB interest income on corporate loans → CCB interest income on loans → CCB interest income on loans → CCB loans and advances → CCB loans and advances → CCB risk-weighted assets? → CCB CET1 ratio → CCB interest income → CCB net interest income → CCB operating income → CCB profit before tax → CCB net profit  (? marks a step whose size is unknown)

Corporate (policy-supported) and household loans respond separately; policy-directed growth comes at thinner spreads, and every loan consumes risk-weighted assets. s31 is the reduced form and is never added to these steps.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [corporate] `ccb-c-credit-corploans` | System credit growth carries the bank's corporate loan growth; the large state banks lend counter-cyclically into policy-supported sectors (infrastructure, technology, manufacturing) (CCB (corporate lending) and policy direction) | loan demand and policy lending quotas; bond financing not substituting for loans; observable: corporate loan growth against total social financing growth | onset within the quarter; build 1-2 quarters; persists while credit growth holds; recognized average balances | documented / documented / unknown / inferred | corporate bond issuance and local government debt swaps replace bank loans | corporate loans | unknown |
| 2 [retail] `ccb-c-credit-otherpers` | Household credit (consumer and personal business loans) follows system credit; it has contracted with household deleveraging (households) | household confidence and income; observable: personal loan growth against system household loans | onset within the quarter; build 1-2 quarters; persists while credit growth holds; recognized average balances | broker / broker / unknown / broker | household deleveraging; tighter consumer-credit standards | other personal loans | unknown |
| 3 `ccb-c-corploans-corpyield` | Counter-path: when corporate loan growth is policy-directed (infrastructure, policy-backed projects) or competed for, it comes at thinner spreads, lowering the average corporate yield (CCB (corporate lending) and policy direction) | growth that is policy-directed or won on price; observable: corporate loan yield against loan growth | onset as loans are booked; build several quarters; persists for the life of the loans; recognized interest income each period | broker / broker / unknown / broker | growth from market-priced demand | corporate loan yield | unknown |
| 4 `ccb-c-corploans-loanii` | More corporate loans earn more interest at a given yield (CCB (corporate lending)) | bilinear: balance times yield; observable: corporate loan balance and loan interest income | onset same period; build none; persists while balances hold; recognized interest income each period | documented / documented / model / documented | the yield falls with the growth (ccb-c-corploans-corpyield) | interest income on loans | +0.80 sd/sd (identity) |
| 5 `ccb-c-otherpers-loanii` | Interest income on consumer and personal business loans is balance times yield (CCB (personal lending)) | bilinear: balance times yield; observable: personal loan balance and loan interest income | onset same period; build none; persists while balances hold; recognized interest income each period | documented / documented / unknown / documented | yield competition | interest income on loans | unknown |
| 6 `ccb-c-corpyield-loanii` | Interest income on corporate loans is the balance times the yield (CCB (corporate lending)) | bilinear: balance times yield; a fixed weight holds only near the current balance; observable: loan yield and loan interest income | onset same period; build none; persists while the yield holds; recognized interest income each period | documented / documented / model / documented | a shrinking book | interest income on loans | +0.56 sd/sd (identity) |
| 7 `ccb-a-lii-corporate-loan-income` | CCB interest income on corporate loans is one part of CCB interest income on loans (interest income on loans by portfolio); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | interest income on loans | +0.96 sd/sd (accounting) |
| 8 `ccb-a-lii-other-loan-income` | CCB interest income on other loans is the residual of CCB interest income on loans: what the named parts leave out, stated in its basis (interest income on loans by portfolio); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | interest income on loans | +0.50 sd/sd (accounting) |
| 9 `ccb-a-loans-corporate-loans` | CCB corporate loans is one part of CCB loans and advances (gross loans and advances by type); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | loans and advances | +0.82 sd/sd (accounting) |
| 10 `ccb-a-loans-other-personal-loans` | CCB other personal loans is one part of CCB loans and advances (gross loans and advances by type); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | loans and advances | +0.21 sd/sd (accounting) |
| 11 `ccb-c-loans-rwa` | Each loan adds risk-weighted assets by its risk weight; mortgages carry low weights, corporate loans high ones, so the mix matters (CCB (capital management)) | standardized or internal-model risk weights unchanged; observable: RWA against loans; RWA density | onset same period; build none; persists while the loans are held; recognized capital reporting each quarter | documented / documented / unknown / broker | risk-weight optimization; a lower-weight mix | risk-weighted assets | unknown |
| 12 `ccb-c-rwa-ratio` | More risk-weighted assets at the same capital lower the CET1 ratio (CCB (capital management)) | capital unchanged; observable: CET1 ratio and RWA, quarterly | onset same reporting date; build none; persists identity; recognized capital reporting each quarter | documented / documented / model / documented | capital grows with the assets | CET1 ratio | -1.40 sd/sd (identity) |
| 13 `ccb-a-ii-loan-interest-income` | CCB interest income on loans is one part of CCB interest income (interest income by earning asset); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | interest income | +0.80 sd/sd (accounting) |
| 14 `ccb-a-nii-interest-income` | CCB interest income is one part of CCB net interest income (net interest income: interest income less interest expense); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | net interest income | +1.62 sd/sd (accounting) |
| 15 `ccb-a-oi-net-interest-income` | CCB net interest income is one part of CCB operating income (operating income by line: net interest income, net fee and commission income and other operating income); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | operating income | +0.77 sd/sd (accounting) |
| 16 `ccb-a-pbt-operating-income` | CCB operating income is one part of CCB profit before tax (profit before tax: operating income less operating expenses less credit impairment); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | profit before tax | +1.54 sd/sd (accounting) |
| 17 `ccb-a-np-profit-before-tax` | CCB profit before tax is one part of CCB net profit (net profit: profit before tax less income tax); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | net profit | +1.46 sd/sd (accounting) |

Unresolved inputs: CET1 capital and ratio (found connected); average loan balances and yields by type (disclosed not supplied); loan growth by type (found proxy); risk weights by portfolio (RWA density) (found connected).

#### CCB deposit repricing and migration

**Trigger:** the large state banks cut posted deposit rates. **Endpoint:** CCB net profit.

CCB posted time deposit rate → [cost] CCB deposit cost? → [migration] CCB customer deposits? → [wealth] CCB agency service fees? → [prepayment] CCB mortgage prepayments? → [mix] CCB time deposit share? → CCB deposit cost? → CCB interest expense on deposits → CCB interest expense on deposits → CCB residential mortgages → CCB interest income on mortgages → CCB interest income on loans → CCB interest expense → CCB net interest income → CCB interest income → CCB net interest income → CCB net fee and commission income → CCB operating income → CCB operating income → CCB profit before tax → CCB net profit  (? marks a step whose size is unknown)

One posted-rate cut, five responses: the cost falls only as time deposits mature, savings migrate to wealth products (slower deposit growth, but distribution fees), households prepay mortgages from savings, and savers term out (a higher time share partly offsets the cut).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [cost] `ccb-c-listrate-depcost` | A posted-rate cut lowers the cost of new and maturing time deposits only; demand deposits pay close to nothing already, so the average cost falls slowly as two- to five-year time deposits mature (CCB (asset-liability management)) | time deposits maturing and renewed at posted rates; observable: deposit cost, half-yearly; time deposits by remaining tenor | onset as time deposits mature; build 1-3 years for the whole book; persists while the posted rate holds; recognized interest expense each period | documented / documented / unknown / broker | savers term out (lock in longer time deposits before further cuts); deposit competition | deposit cost | unknown |
| 2 [migration] `ccb-c-listrate-deposits` | Lower posted deposit rates push savers toward wealth management products, funds and insurance (deposit migration), so the bank's deposits grow more slowly (savers (households and corporates)) | alternatives (wealth products, funds) yield more than deposits; markets calm enough to attract savings; observable: household and non-bank deposit flows; wealth product balances | onset 1-2 quarters; build several quarters; persists while the yield gap lasts; recognized average balances | documented / broker / unknown / broker | market volatility sends savings back to deposits; deposits stay within the banking system as non-bank deposits | customer deposits | unknown |
| 3 [wealth] `ccb-c-listrate-agency` | Counter-path: savings that leave deposits for funds, insurance and wealth products earn the bank distribution (agency) fees, so a deposit-rate cut lifts agency fees (CCB (wealth distribution)) | the bank distributes the products the savings move into; fee-rate caps leave room; observable: agency fee income; new fund issuance | onset 1-2 quarters; build several quarters; persists while the migration lasts; recognized fee income each period | broker / broker / unknown / broker | regulatory fee-rate caps; savings move to products the bank does not sell | agency fees | unknown |
| 4 [prepayment] `ccb-c-listrate-prepay` | When deposit yields fall well below mortgage rates, households use savings to repay mortgages early, shrinking the mortgage book (households (mortgage borrowers)) | a wide gap between mortgage rates and deposit or wealth yields; weak confidence in home prices; observable: mortgage prepayments; mortgage balance against new originations | onset 1-2 quarters; build several quarters; persists while the gap lasts; recognized average balances | broker / inferred / unknown / broker | cuts to existing mortgage rates close the gap; stronger home-buying confidence | mortgage prepayments | unknown |
| 5 [mix] `ccb-c-listrate-timeshare` | As posted rates fall, savers lock in longer time deposits before further cuts and move out of demand deposits, so the time-deposit share rises; the response is state dependent (savers) | time deposits still pay above demand deposits; further cuts expected; observable: time deposits as a share of deposits, half-yearly | onset 1-2 quarters; build several quarters; persists while cuts are expected; recognized deposit mix each period | broker / broker / unknown / broker | cuts that close the gap between time and demand rates; recovering activity that lifts demand deposits | time deposit share | unknown |
| 6 `ccb-c-timeshare-depcost` | Time deposits pay more than demand deposits, so a higher time share raises the average deposit cost (savers) | posted rates unchanged; observable: deposit cost against the time-deposit share | onset same period; build none; persists while the mix holds; recognized interest expense each period | documented / documented / unknown / documented | a narrowing gap between time and demand rates | deposit cost | unknown |
| 7 `ccb-c-depcost-depexp` | Interest expense on deposits is the balance times the deposit cost; a higher cost makes the (negative) expense larger (CCB (asset-liability management)) | bilinear: balance times cost; observable: deposit cost and deposit interest expense | onset same period; build none; persists while the cost holds; recognized interest expense each period | documented / documented / model / documented | a falling deposit balance | interest expense on deposits | -1.30 sd/sd (identity) |
| 8 `ccb-c-deposits-depexp` | Interest expense on deposits is the balance times the cost; a larger balance makes the (negative) expense larger (CCB (asset-liability management)) | bilinear: balance times cost; observable: deposit balance and deposit interest expense | onset same period; build none; persists while balances hold; recognized interest expense each period | documented / documented / model / documented | falling deposit cost | interest expense on deposits | -0.78 sd/sd (identity) |
| 9 `ccb-c-prepay-mortgages` | Prepayments run the mortgage book down; with weak new originations the book is flat or shrinking (households) | prepayments above scheduled amortization; observable: mortgage balance and prepayments | onset same period; build cumulative; persists permanent for the loans repaid; recognized average balances | broker / documented / model / broker | a pickup in home sales and new originations | residential mortgages | -0.96 sd/sd (stock-flow, accumulates per 365 days) |
| 10 `ccb-c-mortgages-loanii` | Interest income on mortgages is the balance times the yield; a shrinking book earns less (CCB (personal lending)) | bilinear: balance times yield; observable: mortgage balance and loan interest income | onset same period; build none; persists while balances hold; recognized interest income each period | documented / documented / model / documented | the freed funding is relent at similar yields | interest income on loans | +0.75 sd/sd (identity) |
| 11 `ccb-a-lii-mortgage-income` | CCB interest income on mortgages is one part of CCB interest income on loans (interest income on loans by portfolio); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | interest income on loans | +0.24 sd/sd (accounting) |
| 12 `ccb-a-ie-deposit-interest-expense` | CCB interest expense on deposits is one part of CCB interest expense (interest expense by funding source (negative values)); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | interest expense | +0.80 sd/sd (accounting) |
| 13 `ccb-a-nii-interest-expense` | CCB interest expense is one part of CCB net interest income (net interest income: interest income less interest expense); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | net interest income | +1.08 sd/sd (accounting) |
| 14 `ccb-a-ii-loan-interest-income` | CCB interest income on loans is one part of CCB interest income (interest income by earning asset); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | interest income | +0.80 sd/sd (accounting) |
| 15 `ccb-a-nii-interest-income` | CCB interest income is one part of CCB net interest income (net interest income: interest income less interest expense); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | net interest income | +1.62 sd/sd (accounting) |
| 16 `ccb-a-fee-agency-fees` | CCB agency service fees is one part of CCB net fee and commission income (net fee and commission income by product); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | net fee and commission income | +0.46 sd/sd (accounting) |
| 17 `ccb-a-oi-net-fee-income` | CCB net fee and commission income is one part of CCB operating income (operating income by line: net interest income, net fee and commission income and other operating income); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | operating income | +0.22 sd/sd (accounting) |
| 18 `ccb-a-oi-net-interest-income` | CCB net interest income is one part of CCB operating income (operating income by line: net interest income, net fee and commission income and other operating income); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | operating income | +0.77 sd/sd (accounting) |
| 19 `ccb-a-pbt-operating-income` | CCB operating income is one part of CCB profit before tax (profit before tax: operating income less operating expenses less credit impairment); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | profit before tax | +1.54 sd/sd (accounting) |
| 20 `ccb-a-np-profit-before-tax` | CCB profit before tax is one part of CCB net profit (net profit: profit before tax less income tax); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | net profit | +1.46 sd/sd (accounting) |

Unresolved inputs: agency fee income by product (funds, bancassurance, wealth management products) (disclosed not supplied); average deposit balances and cost (demand versus time) (disclosed not supplied); average loan balances and yields by type (disclosed not supplied); deposit maturity profile (time deposits by remaining tenor) (disclosed not supplied); deposit migration to wealth management products (volumes) (found proxy); mortgage prepayment rate (not disclosed in reviewed sources); mortgage share of total loans (found connected); regulatory fee-rate caps (bancassurance, fund distribution) (found connected).

#### CCB loan prime rate to net interest income

**Trigger:** the PBoC guides the loan prime rate down. **Endpoint:** CCB net profit.

1-year loan prime rate → [corporate] CCB corporate loan yield? → [mortgage] 5-year loan prime rate? → [deposits] CCB posted time deposit rate? → [bonds] CGB 10Y yield → [volume] China total social financing growth → CCB mortgage yield? → CCB deposit cost? → CCB bond new-purchase yield? → CCB financial investment yield? → CCB corporate loans? → CCB interest income on corporate loans → CCB interest income on mortgages → CCB interest expense on deposits → CCB interest income on financial investments → CCB interest income on corporate loans → CCB interest income on loans → CCB interest income on loans → CCB interest income → CCB interest income → CCB interest expense → CCB net interest income → CCB net interest income → CCB net interest margin → CCB operating income → CCB profit before tax → CCB net profit  (? marks a step whose size is unknown)

Parallel responses of one LPR move: corporate loans reprice off the 1-year LPR, mortgages off the 5-year LPR at their reset date, deposits only through posted-rate cuts and maturities, the bond curve follows, and credit demand responds. Assets reprice faster than deposits, so a cut squeezes NII before deposit cuts catch up. s27 and s29 are the reduced forms (LPR to NIM, NIM to net profit) and are never added to these steps.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [corporate] `ccb-c-lpr-corpyield` | Corporate loans are priced at a spread to the 1-year LPR: new loans price off the current LPR at once, existing floating loans move on their repricing date; competition for scarce loan demand deepens discounts below the LPR (CCB (corporate lending and pricing)) | loans priced off the LPR rather than fixed; repricing dates spread over the year; observable: average corporate loan yield against the 1-year LPR, half-yearly; new-loan pricing in PBoC data | onset new loans at once; existing loans at their repricing date; build up to 12 months as the book reprices; persists while the LPR holds; recognized interest income each period | documented / documented / unknown / broker | loan demand weak enough that discounts widen regardless of the LPR; policy-directed lending at thin spreads | corporate loan yield | unknown |
| 2 [mortgage] `ccb-c-lpr-lpr5y` | The panel banks quote both LPR tenors on the same day; a 1-year cut usually comes with a 5-year cut, but the two tenors have moved by different amounts (the 5-year more when housing is the policy target) (LPR panel banks under PBoC guidance) | an LPR fixing that moves both tenors; observable: monthly LPR fixings (1-year and 5-year) | onset same fixing day; build none; persists until the next fixing; recognized benchmark only | documented / documented / unknown / documented | a targeted move in one tenor only (housing support through the 5-year tenor) | 5-year LPR | unknown |
| 3 [deposits] `ccb-c-lpr-listrate` | After LPR cuts the large state banks cut posted deposit rates (through the interest-rate self-regulatory mechanism) to protect margins; the lag has varied from a year to the same quarter (CCB and the large state banks (asset-liability pricing)) | margins under pressure and the deposit market orderly enough for coordinated cuts; observable: posted time deposit rates of the large banks against the LPR | onset weeks to quarters after the LPR move; build none (a posted-rate change); persists until the next cut; recognized deposit cost only as deposits reprice | documented / documented / unknown / broker | deposit competition for scarce funding; a policy wish to protect savers' income | posted time deposit rate | unknown |
| 4 [bonds] `s56` | 1-year loan prime rate anchors CGB 10Y yield | unknown | unknown | unknown | unknown | unknown | +0.60 sd/sd |
| 5 [volume] `s03` | 1-year loan prime rate cuts lift credit China total social financing growth | unknown | unknown | unknown | unknown | unknown | -0.40 sd/sd |
| 6 `ccb-c-lpr5y-mortyield` | Existing mortgages reset to the 5-year LPR plus their fixed spread on the annual repricing date (usually the first of January); new mortgages price off the current 5-year LPR, above a pricing floor (CCB (personal lending)) | floating mortgages on annual reset; the pricing floor not binding; observable: average mortgage yield, half-yearly; new mortgage pricing against the 5-year LPR | onset new mortgages at once; the book at its next repricing date; build one reset cycle (up to 12 months); persists while the LPR holds; recognized interest income each period | documented / documented / unknown / documented | a pricing floor on new mortgages; administrative cuts to existing mortgage rates outside the LPR; prepayment of high-rate loans | mortgage yield | unknown |
| 7 `ccb-c-listrate-depcost` | A posted-rate cut lowers the cost of new and maturing time deposits only; demand deposits pay close to nothing already, so the average cost falls slowly as two- to five-year time deposits mature (CCB (asset-liability management)) | time deposits maturing and renewed at posted rates; observable: deposit cost, half-yearly; time deposits by remaining tenor | onset as time deposits mature; build 1-3 years for the whole book; persists while the posted rate holds; recognized interest expense each period | documented / documented / unknown / broker | savers term out (lock in longer time deposits before further cuts); deposit competition | deposit cost | unknown |
| 8 `ccb-c-cgb-npy` | The treasury buys government, local government and policy-bank bonds at prevailing yields, so new-purchase yields follow the curve (CCB treasury) | purchases spread across tenors near the 10-year point; observable: yield on bonds bought in the period | onset at purchase; build none; persists to maturity; recognized accrual each period | documented / inferred / unknown / unknown | a shift in tenor or issuer mix (local government bonds above the CGB curve) | bond new-purchase yield | unknown |
| 9 `ccb-c-npy-invyield` | Each year's purchases replace maturing bonds, so the book yield drifts toward new-purchase yields at the pace of maturities (CCB treasury) | bonds maturing and reinvested in bonds (not held as reserves or lent); observable: book yield on financial investments, half-yearly | onset as bonds mature; build years (the book's remaining life); persists to maturity; recognized interest income each period | documented / documented / unknown / inferred | the treasury holds cash or lends instead of reinvesting | financial investment yield | unknown |
| 10 `ccb-c-credit-corploans` | System credit growth carries the bank's corporate loan growth; the large state banks lend counter-cyclically into policy-supported sectors (infrastructure, technology, manufacturing) (CCB (corporate lending) and policy direction) | loan demand and policy lending quotas; bond financing not substituting for loans; observable: corporate loan growth against total social financing growth | onset within the quarter; build 1-2 quarters; persists while credit growth holds; recognized average balances | documented / documented / unknown / inferred | corporate bond issuance and local government debt swaps replace bank loans | corporate loans | unknown |
| 11 `ccb-c-corpyield-loanii` | Interest income on corporate loans is the balance times the yield (CCB (corporate lending)) | bilinear: balance times yield; a fixed weight holds only near the current balance; observable: loan yield and loan interest income | onset same period; build none; persists while the yield holds; recognized interest income each period | documented / documented / model / documented | a shrinking book | interest income on loans | +0.56 sd/sd (identity) |
| 12 `ccb-c-mortyield-loanii` | Interest income on mortgages is the balance times the mortgage yield (CCB (personal lending)) | bilinear: balance times yield; observable: mortgage yield and loan interest income | onset same period; build none; persists while the yield holds; recognized interest income each period | documented / documented / model / documented | a shrinking mortgage book (prepayments) | interest income on loans | +0.74 sd/sd (identity) |
| 13 `ccb-c-depcost-depexp` | Interest expense on deposits is the balance times the deposit cost; a higher cost makes the (negative) expense larger (CCB (asset-liability management)) | bilinear: balance times cost; observable: deposit cost and deposit interest expense | onset same period; build none; persists while the cost holds; recognized interest expense each period | documented / documented / model / documented | a falling deposit balance | interest expense on deposits | -1.30 sd/sd (identity) |
| 14 `ccb-c-invyield-invii` | Interest income on financial investments is the average balance times the book yield (CCB treasury) | bilinear: balance times yield; observable: book yield and investment interest income | onset same period; build none; persists while held; recognized interest income each period | documented / documented / model / documented | a shrinking book | interest income on financial investments | +0.60 sd/sd (identity) |
| 15 `ccb-c-corploans-loanii` | More corporate loans earn more interest at a given yield (CCB (corporate lending)) | bilinear: balance times yield; observable: corporate loan balance and loan interest income | onset same period; build none; persists while balances hold; recognized interest income each period | documented / documented / model / documented | the yield falls with the growth (ccb-c-corploans-corpyield) | interest income on loans | +0.80 sd/sd (identity) |
| 16 `ccb-a-lii-corporate-loan-income` | CCB interest income on corporate loans is one part of CCB interest income on loans (interest income on loans by portfolio); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | interest income on loans | +0.96 sd/sd (accounting) |
| 17 `ccb-a-lii-mortgage-income` | CCB interest income on mortgages is one part of CCB interest income on loans (interest income on loans by portfolio); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | interest income on loans | +0.24 sd/sd (accounting) |
| 18 `ccb-a-ii-loan-interest-income` | CCB interest income on loans is one part of CCB interest income (interest income by earning asset); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | interest income | +0.80 sd/sd (accounting) |
| 19 `ccb-a-ii-investment-interest-income` | CCB interest income on financial investments is one part of CCB interest income (interest income by earning asset); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | interest income | +0.21 sd/sd (accounting) |
| 20 `ccb-a-ie-deposit-interest-expense` | CCB interest expense on deposits is one part of CCB interest expense (interest expense by funding source (negative values)); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | interest expense | +0.80 sd/sd (accounting) |
| 21 `ccb-a-nii-interest-income` | CCB interest income is one part of CCB net interest income (net interest income: interest income less interest expense); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | net interest income | +1.62 sd/sd (accounting) |
| 22 `ccb-a-nii-interest-expense` | CCB interest expense is one part of CCB net interest income (net interest income: interest income less interest expense); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | net interest income | +1.08 sd/sd (accounting) |
| 23 `ccb-c-nii-nim` | NIM is net interest income over average interest-earning assets: a ratio, not a cause (CCB (reporting)) | same period and averaging basis; observable: reported NIM against NII and average earning assets | onset same period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | never calibrated beside s29 (NIM to net profit): NII already reaches net profit through the accounts | net interest margin | +1.14 sd/sd (identity) |
| 24 `ccb-a-oi-net-interest-income` | CCB net interest income is one part of CCB operating income (operating income by line: net interest income, net fee and commission income and other operating income); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | operating income | +0.77 sd/sd (accounting) |
| 25 `ccb-a-pbt-operating-income` | CCB operating income is one part of CCB profit before tax (profit before tax: operating income less operating expenses less credit impairment); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | profit before tax | +1.54 sd/sd (accounting) |
| 26 `ccb-a-np-profit-before-tax` | CCB profit before tax is one part of CCB net profit (net profit: profit before tax less income tax); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | net profit | +1.46 sd/sd (accounting) |

Unresolved inputs: NII sensitivity to an LPR cut (repricing gap by tenor) (disclosed not supplied); NIM history (found not connected); average deposit balances and cost (demand versus time) (disclosed not supplied); average loan balances and yields by type (disclosed not supplied); deposit maturity profile (time deposits by remaining tenor) (disclosed not supplied); financial investments: book yield, maturities and new-purchase yields (disclosed not supplied); loan growth by type (found proxy); mortgage repricing date and spread over the 5-year LPR (not disclosed in reviewed sources); posted deposit rate cuts and their effective dates (found connected); share of corporate loans priced off the LPR and their repricing dates (not disclosed in reviewed sources); the spread between the 1-year and 5-year LPR moves (found connected).

#### CCB fiscal mortgage subsidy to asset quality

**Trigger:** the government funds an interest subsidy on eligible first-home mortgages. **Endpoint:** CCB net profit.

China first-home mortgage interest subsidy → [repayment] CCB mortgage NPL ratio? → [demand] China property sales? → CCB residential mortgages? → CCB non-performing loan ratio → CCB loan allowance build? → CCB net loan write-offs? → CCB interest income on mortgages → CCB interest income on loans → CCB loan impairment losses → CCB loan impairment losses → CCB credit impairment losses → CCB profit before tax → CCB interest income → CCB net interest income → CCB operating income → CCB profit before tax → CCB net profit  (? marks a step whose size is unknown)

Policy support paid by the budget, not by bank pricing: borrowers' effective cost falls (better mortgage quality) and first-home demand firms (more originations), while the bank's loan yield is unchanged, so there is no NIM step. It may also lessen the need for further LPR cuts (a policy substitution not held as a link).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [repayment] `ccb-c-subsidy-mortnpl` | A fiscally funded interest subsidy lowers eligible borrowers' effective mortgage cost and so their default risk; the bank's own loan rate is unchanged (the subsidy is not bank pricing) (central and local government (fiscal); households) | eligible first-home loans in the bank's book (price and size caps); observable: subsidized mortgage balance; mortgage NPL ratio | onset from the effective date; build years (applies to new eligible loans); persists the subsidy period; recognized NPL classification over time | broker / broker / unknown / broker | narrow eligibility (higher-tier city prices above the cap); the subsidy lapses | mortgage NPL ratio | unknown |
| 2 [demand] `ccb-c-subsidy-propsales` | Lower effective mortgage costs support first-home purchases, modestly given weak sentiment (households (first-home buyers)) | eligible buyers in lower-tier cities; observable: home sales after the effective date | onset 1-2 quarters; build several quarters; persists the subsidy period; recognized property sales data | broker / broker / unknown / broker | weak sentiment and price expectations; eligibility caps | property sales | unknown |
| 3 `ccb-c-prop-mortgages` | Mortgage originations follow home purchases; with sales weak and prepayments high the book is flat or shrinking (home buyers) | the bank keeps its share of new mortgages; observable: new mortgage originations; mortgage balance | onset 1-2 quarters; build several quarters; persists while sales hold; recognized average balances | broker / broker / unknown / broker | prepayments outrun originations (ccb-c-prepay-mortgages) | residential mortgages | unknown |
| 4 `ccb-c-mortnpl-npl` | The group NPL ratio is the loan-weighted average of portfolio NPL ratios; mortgages are a large share of loans at this bank (CCB (reporting)) | loan mix unchanged; observable: group and portfolio NPL ratios, half-yearly | onset same reporting date; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | a shifting loan mix | NPL ratio | +0.32 sd/sd (identity) |
| 5 `ccb-c-npl-allowance` | Loans moving into default (stage 3) need lifetime expected-loss reserves, so a rising NPL ratio raises the allowance build (CCB (allowance process)) | migration at the reporting date; observable: stage 3 loans and their allowance | onset reporting date; build 1-2 reporting periods; persists until written off; recognized impairment charge that period | documented / documented / unknown / inferred | a release from the coverage buffer (ccb-c-coverage-allowance) | loan allowance build | unknown |
| 6 `ccb-c-npl-writeoffs` | Non-performing loans are written off or disposed of (transfers to asset managers, securitization) with a lag, charging the allowance (CCB (special assets)) | recovery prospects exhausted; disposal channels open; observable: write-offs and disposals of NPLs | onset 2-6 quarters; build several quarters; persists the credit cycle; recognized charged through the allowance | documented / documented / unknown / inferred | recoveries; restructuring rather than write-off | net loan write-offs | unknown |
| 7 `ccb-c-mortgages-loanii` | Interest income on mortgages is the balance times the yield; a shrinking book earns less (CCB (personal lending)) | bilinear: balance times yield; observable: mortgage balance and loan interest income | onset same period; build none; persists while balances hold; recognized interest income each period | documented / documented / model / documented | the freed funding is relent at similar yields | interest income on loans | +0.75 sd/sd (identity) |
| 8 `ccb-a-lii-mortgage-income` | CCB interest income on mortgages is one part of CCB interest income on loans (interest income on loans by portfolio); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | interest income on loans | +0.24 sd/sd (accounting) |
| 9 `ccb-a-limp-allowance-build` | CCB loan allowance build is one part of CCB loan impairment losses (loan impairment: net write-offs plus allowance build (allowance roll-forward)); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | loan impairment losses | +0.83 sd/sd (accounting) |
| 10 `ccb-a-limp-net-write-offs` | CCB net loan write-offs is one part of CCB loan impairment losses (loan impairment: net write-offs plus allowance build (allowance roll-forward)); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | loan impairment losses | +0.67 sd/sd (accounting) |
| 11 `ccb-a-cimp-loan-impairment` | CCB loan impairment losses is one part of CCB credit impairment losses (credit impairment losses by asset (negative values)); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | credit impairment losses | +0.90 sd/sd (accounting) |
| 12 `ccb-a-pbt-credit-impairment` | CCB credit impairment losses is one part of CCB profit before tax (profit before tax: operating income less operating expenses less credit impairment); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | profit before tax | +1.03 sd/sd (accounting) |
| 13 `ccb-a-ii-loan-interest-income` | CCB interest income on loans is one part of CCB interest income (interest income by earning asset); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | interest income | +0.80 sd/sd (accounting) |
| 14 `ccb-a-nii-interest-income` | CCB interest income is one part of CCB net interest income (net interest income: interest income less interest expense); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | net interest income | +1.62 sd/sd (accounting) |
| 15 `ccb-a-oi-net-interest-income` | CCB net interest income is one part of CCB operating income (operating income by line: net interest income, net fee and commission income and other operating income); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | operating income | +0.77 sd/sd (accounting) |
| 16 `ccb-a-pbt-operating-income` | CCB operating income is one part of CCB profit before tax (profit before tax: operating income less operating expenses less credit impairment); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | profit before tax | +1.54 sd/sd (accounting) |
| 17 `ccb-a-np-profit-before-tax` | CCB profit before tax is one part of CCB net profit (net profit: profit before tax less income tax); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | net profit | +1.46 sd/sd (accounting) |

Unresolved inputs: average loan balances and yields by type (disclosed not supplied); credit cost (impairment over loans) (found not connected); eligible first-home mortgage volume under the subsidy (not disclosed in reviewed sources); mortgage NPL ratio (disclosed not supplied); mortgage prepayment rate (not disclosed in reviewed sources); mortgage share of total loans (found connected); provision coverage ratio and the regulatory floor (disclosed not supplied).

#### CCB property market to asset quality and credit cost

**Trigger:** property sales fall. **Endpoint:** CCB net profit.

China property sales → [mortgage_quality] CCB mortgage NPL ratio? → [developer_quality] CCB developer loan NPL ratio? → [volume] CCB residential mortgages? → [outlook] CCB loan allowance build? → CCB non-performing loan ratio → CCB non-performing loan ratio → CCB net loan write-offs? → CCB loan allowance build? → CCB non-performing loans → CCB provision coverage ratio → CCB loan allowance build? → CCB loan loss reserve → CCB provision coverage ratio → CCB interest income on mortgages → CCB interest income on loans → CCB loan impairment losses → CCB loan impairment losses → CCB credit impairment losses → CCB profit before tax → CCB interest income → CCB net interest income → CCB operating income → CCB profit before tax → CCB net profit  (? marks a step whose size is unknown)

A weaker property market reaches the bank four ways at once: mortgage NPLs (slow, low loan-to-value), developer NPLs (faster), fewer new mortgages, and a worse IFRS 9 outlook (an allowance build before any default). NPLs feed write-offs and stage-3 reserves; a thick coverage buffer lets the bank smooth the charge. s28 and s30 are the reduced forms and are never added to these steps.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [mortgage_quality] `ccb-c-prop-mortnpl` | Falling home sales and prices weaken household repayment capacity and collateral, so mortgage delinquencies and NPLs rise (slowly: recourse lending with large down payments) (households (mortgage borrowers)) | falling prices in the cities where the book sits; income stress; observable: mortgage NPL ratio, half-yearly | onset 2-4 quarters; build several quarters; persists the property cycle; recognized NPL classification at the reporting date | broker / broker / unknown / broker | low loan-to-value ratios and full recourse; policy support (subsidies, rate cuts) | mortgage NPL ratio | unknown |
| 2 [developer_quality] `ccb-c-prop-devnpl` | Developers fund themselves from presales; weaker sales cut their cash flow and raise defaults on development loans (property developers) | developers dependent on presales; funding channels closed; observable: real estate corporate loan NPL ratio, half-yearly | onset 1-3 quarters; build several quarters; persists the property cycle; recognized NPL classification at the reporting date | broker / broker / unknown / broker | the bank's exposure to developers shrinking; white-list project financing; state-backed developers | developer loan NPL ratio | unknown |
| 3 [volume] `ccb-c-prop-mortgages` | Mortgage originations follow home purchases; with sales weak and prepayments high the book is flat or shrinking (home buyers) | the bank keeps its share of new mortgages; observable: new mortgage originations; mortgage balance | onset 1-2 quarters; build several quarters; persists while sales hold; recognized average balances | broker / broker / unknown / broker | prepayments outrun originations (ccb-c-prepay-mortgages) | residential mortgages | unknown |
| 4 [outlook] `ccb-c-prop-allowance` | IFRS 9 allowances weigh forward-looking scenarios (home prices and sales among them): a better property outlook lowers expected credit loss at once, before any NPL changes (CCB (credit risk, allowance process)) | scenario or weight change at the reporting date; observable: loan loss allowance and its staging | onset reporting date; build 1-2 reporting periods; persists until the outlook changes; recognized impairment charge that period | documented / inferred / unknown / inferred | management overlays already held; the bank chooses to keep the buffer | loan allowance build | unknown |
| 5 `ccb-c-mortnpl-npl` | The group NPL ratio is the loan-weighted average of portfolio NPL ratios; mortgages are a large share of loans at this bank (CCB (reporting)) | loan mix unchanged; observable: group and portfolio NPL ratios, half-yearly | onset same reporting date; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | a shifting loan mix | NPL ratio | +0.32 sd/sd (identity) |
| 6 `ccb-c-devnpl-npl` | Developer loans are a small share of loans, so even a high developer NPL ratio moves the group ratio modestly (CCB (reporting)) | loan mix unchanged; observable: group and portfolio NPL ratios, half-yearly | onset same reporting date; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | developer exposure shrinking | NPL ratio | +0.32 sd/sd (identity) |
| 7 `ccb-c-npl-writeoffs` | Non-performing loans are written off or disposed of (transfers to asset managers, securitization) with a lag, charging the allowance (CCB (special assets)) | recovery prospects exhausted; disposal channels open; observable: write-offs and disposals of NPLs | onset 2-6 quarters; build several quarters; persists the credit cycle; recognized charged through the allowance | documented / documented / unknown / inferred | recoveries; restructuring rather than write-off | net loan write-offs | unknown |
| 8 `ccb-c-npl-allowance` | Loans moving into default (stage 3) need lifetime expected-loss reserves, so a rising NPL ratio raises the allowance build (CCB (allowance process)) | migration at the reporting date; observable: stage 3 loans and their allowance | onset reporting date; build 1-2 reporting periods; persists until written off; recognized impairment charge that period | documented / documented / unknown / inferred | a release from the coverage buffer (ccb-c-coverage-allowance) | loan allowance build | unknown |
| 9 `ccb-c-npl-npls` | Non-performing loans outstanding are the NPL ratio times gross loans (CCB (reporting)) | same reporting date; observable: NPL balance and ratio, half-yearly | onset same reporting date; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | none | non-performing loans | +0.75 sd/sd (identity) |
| 10 `ccb-c-npl-coverage` | Provision coverage is the allowance over NPLs: more NPLs at the same allowance lower it (CCB (reporting)) | allowance unchanged; observable: provision coverage ratio, half-yearly | onset same reporting date; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | an allowance build | provision coverage ratio | -1.15 sd/sd (identity) |
| 11 `ccb-c-coverage-allowance` | Counter-path: with coverage well above the regulatory floor, the bank can provide less (or release reserves) to steady reported profit, and rebuild it when earnings allow (CCB management (provisioning policy)) | coverage above the regulatory floor and the bank's own target; observable: provision coverage ratio; credit cost | onset reporting date; build none; persists management choice; recognized impairment charge that period | broker / broker / unknown / broker | coverage near the floor; regulators asking for countercyclical buffers | loan allowance build | unknown; acts only while CCB provision coverage ratio is above 150 |
| 12 `ccb-c-allowance-reserve` | The allowance build charged to profit accumulates in the loan loss reserve (a build is held negative, so a larger build raises the reserve); write-offs net of recoveries draw it down inside the charge (CCB (allowance process)) | accumulation over the year; observable: loan loss reserve roll-forward | onset period end; build cumulative; persists until written off; recognized interim and annual results | documented / documented / model / documented | none | loan loss reserve | -0.38 sd/sd (stock-flow, accumulates per 365 days) |
| 13 `ccb-c-reserve-coverage` | Provision coverage is the loan loss reserve over non-performing loans (CCB (reporting)) | NPLs unchanged; observable: provision coverage ratio, half-yearly | onset same reporting date; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | none | provision coverage ratio | +1.16 sd/sd (identity) |
| 14 `ccb-c-mortgages-loanii` | Interest income on mortgages is the balance times the yield; a shrinking book earns less (CCB (personal lending)) | bilinear: balance times yield; observable: mortgage balance and loan interest income | onset same period; build none; persists while balances hold; recognized interest income each period | documented / documented / model / documented | the freed funding is relent at similar yields | interest income on loans | +0.75 sd/sd (identity) |
| 15 `ccb-a-lii-mortgage-income` | CCB interest income on mortgages is one part of CCB interest income on loans (interest income on loans by portfolio); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | interest income on loans | +0.24 sd/sd (accounting) |
| 16 `ccb-a-limp-net-write-offs` | CCB net loan write-offs is one part of CCB loan impairment losses (loan impairment: net write-offs plus allowance build (allowance roll-forward)); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | loan impairment losses | +0.67 sd/sd (accounting) |
| 17 `ccb-a-limp-allowance-build` | CCB loan allowance build is one part of CCB loan impairment losses (loan impairment: net write-offs plus allowance build (allowance roll-forward)); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | loan impairment losses | +0.83 sd/sd (accounting) |
| 18 `ccb-a-cimp-loan-impairment` | CCB loan impairment losses is one part of CCB credit impairment losses (credit impairment losses by asset (negative values)); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | credit impairment losses | +0.90 sd/sd (accounting) |
| 19 `ccb-a-pbt-credit-impairment` | CCB credit impairment losses is one part of CCB profit before tax (profit before tax: operating income less operating expenses less credit impairment); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | profit before tax | +1.03 sd/sd (accounting) |
| 20 `ccb-a-ii-loan-interest-income` | CCB interest income on loans is one part of CCB interest income (interest income by earning asset); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | interest income | +0.80 sd/sd (accounting) |
| 21 `ccb-a-nii-interest-income` | CCB interest income is one part of CCB net interest income (net interest income: interest income less interest expense); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | net interest income | +1.62 sd/sd (accounting) |
| 22 `ccb-a-oi-net-interest-income` | CCB net interest income is one part of CCB operating income (operating income by line: net interest income, net fee and commission income and other operating income); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | operating income | +0.77 sd/sd (accounting) |
| 23 `ccb-a-pbt-operating-income` | CCB operating income is one part of CCB profit before tax (profit before tax: operating income less operating expenses less credit impairment); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | profit before tax | +1.54 sd/sd (accounting) |
| 24 `ccb-a-np-profit-before-tax` | CCB profit before tax is one part of CCB net profit (net profit: profit before tax less income tax); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | net profit | +1.46 sd/sd (accounting) |

Unresolved inputs: ECL scenario weights and macro assumptions (house prices, sales) (disclosed not supplied); average loan balances and yields by type (disclosed not supplied); credit cost (impairment over loans) (found not connected); developer loan NPL ratio and real estate exposure (found proxy); mortgage NPL ratio (disclosed not supplied); mortgage prepayment rate (not disclosed in reviewed sources); mortgage share of total loans (found connected); provision coverage ratio and the regulatory floor (disclosed not supplied).

#### CCB bond reinvestment below the book yield

**Trigger:** bonds bought at higher yields mature while new-purchase yields sit below the book yield. **Endpoint:** CCB net profit.

CCB bond maturities and redemptions → CCB financial investment yield? → CCB interest income on financial investments → CCB interest income → CCB net interest income → CCB operating income → CCB profit before tax → CCB net profit → [capital] CCB CET1 capital  (? marks a step whose size is unknown)

Maturities -> reinvestment at lower yields -> book yield -> interest income -> NII -> operating income -> profit -> capital. The maturity ladder is not in the supplied material, so no new yield is applied to the whole book.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `ccb-c-maturities-invyield` | Maturing bonds bought when yields were higher are reinvested at today's lower yields, so the more that matures, the faster the book yield falls; the sign holds only while new-purchase yields sit below the book yield (CCB treasury (reinvestment decision)) | new-purchase yields below the book yield of what matures; observable: book yield on financial investments against new-purchase yields, half-yearly | onset as bonds mature; build cohort by cohort; persists to maturity of the new purchases; recognized interest income each period | documented / inferred / unknown / inferred | new-purchase yields above the book yield reverse the sign; the treasury holds the cash as reserves | financial investment yield | unknown; sign as stated while CCB bond new-purchase yield is below 2.5, reversed otherwise |
| 2 `ccb-c-invyield-invii` | Interest income on financial investments is the average balance times the book yield (CCB treasury) | bilinear: balance times yield; observable: book yield and investment interest income | onset same period; build none; persists while held; recognized interest income each period | documented / documented / model / documented | a shrinking book | interest income on financial investments | +0.60 sd/sd (identity) |
| 3 `ccb-a-ii-investment-interest-income` | CCB interest income on financial investments is one part of CCB interest income (interest income by earning asset); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | interest income | +0.21 sd/sd (accounting) |
| 4 `ccb-a-nii-interest-income` | CCB interest income is one part of CCB net interest income (net interest income: interest income less interest expense); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | net interest income | +1.62 sd/sd (accounting) |
| 5 `ccb-a-oi-net-interest-income` | CCB net interest income is one part of CCB operating income (operating income by line: net interest income, net fee and commission income and other operating income); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | operating income | +0.77 sd/sd (accounting) |
| 6 `ccb-a-pbt-operating-income` | CCB operating income is one part of CCB profit before tax (profit before tax: operating income less operating expenses less credit impairment); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | profit before tax | +1.54 sd/sd (accounting) |
| 7 `ccb-a-np-profit-before-tax` | CCB profit before tax is one part of CCB net profit (net profit: profit before tax less income tax); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | net profit | +1.46 sd/sd (accounting) |
| 8 [capital] `ccb-c-np-cet1` | Net profit adds to retained earnings and so to CET1 capital (a flow into a stock: next period's capital is this period's plus profit less dividends) (group) | accumulation over the period; observable: CET1 capital roll-forward | onset period end; build cumulative; persists permanent; recognized capital reporting each quarter | documented / documented / model / documented | dividends above profit | CET1 capital | +0.22 sd/sd (stock-flow, accumulates per 365 days) |

Unresolved inputs: CET1 capital and ratio (found connected); financial investments: book yield, maturities and new-purchase yields (disclosed not supplied).

#### CCB state capital injection

**Trigger:** the state injects core tier 1 capital. **Endpoint:** CCB CET1 ratio.

CCB state capital injection → CCB CET1 capital → CCB CET1 ratio

Government support as shareholder: capital in at once, raising the ratio (and the room for lending and dividends).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `ccb-c-injection-cet1` | The state injects core tier 1 capital into the large banks (a share placement funded by special government bonds), adding to CET1 at once; it supports lending capacity and dividends, and dilutes per-share figures (Ministry of Finance (state shareholder)) | a state decision to recapitalize the large banks; observable: share placement to the state; CET1 capital | onset at completion of the placement; build none; persists permanent; recognized capital reporting at completion | broker / broker / model / broker | none known; the size and timing are policy decisions | CET1 capital | +0.67 sd/sd (stock-flow, accumulates per 365 days) |
| 2 `ccb-c-cet1cap-ratio` | The CET1 ratio is CET1 capital over risk-weighted assets (CCB (capital management)) | RWA unchanged; observable: CET1 ratio, quarterly | onset same reporting date; build none; persists identity; recognized capital reporting each quarter | documented / documented / model / documented | RWA growth | CET1 ratio | +0.95 sd/sd (identity) |

Unresolved inputs: CET1 capital and ratio (found connected); state capital injection amount and date (found connected).

#### CCB capital markets to wealth distribution fees

**Trigger:** Chinese equity markets rise. **Endpoint:** CCB net profit.

China equity index (CSI 300) → CCB agency service fees? → CCB net fee and commission income → CCB operating income → CCB profit before tax → CCB net profit  (? marks a step whose size is unknown)

Fund and wealth product sales follow the market; regulatory fee-rate caps limit what the bank earns per sale.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `ccb-c-equity-agency` | Rising equity markets lift fund sales and wealth product demand, so agency (distribution) fees rise (CCB (wealth distribution); retail investors) | fund issuance responds to the market; fee-rate caps leave room; observable: agency fee income; new fund issuance; A-share turnover | onset weeks; build 1-2 quarters; persists while markets hold; recognized fee income each period | broker / broker / unknown / broker | regulatory fee-rate caps (bancassurance, fund distribution) | agency fees | unknown |
| 2 `ccb-a-fee-agency-fees` | CCB agency service fees is one part of CCB net fee and commission income (net fee and commission income by product); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | net fee and commission income | +0.46 sd/sd (accounting) |
| 3 `ccb-a-oi-net-fee-income` | CCB net fee and commission income is one part of CCB operating income (operating income by line: net interest income, net fee and commission income and other operating income); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | operating income | +0.22 sd/sd (accounting) |
| 4 `ccb-a-pbt-operating-income` | CCB operating income is one part of CCB profit before tax (profit before tax: operating income less operating expenses less credit impairment); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | profit before tax | +1.54 sd/sd (accounting) |
| 5 `ccb-a-np-profit-before-tax` | CCB profit before tax is one part of CCB net profit (net profit: profit before tax less income tax); weight is its scale over the total's | IFRS, group, same period, RMB bn; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized interim and annual results | documented / documented / model / documented | unknown | net profit | +1.46 sd/sd (accounting) |

Unresolved inputs: agency fee income by product (funds, bancassurance, wealth management products) (disclosed not supplied); regulatory fee-rate caps (bancassurance, fund distribution) (found connected).

## Validation

`tests/scenario/test_construction_china_construction_bank.py` (loads sally_demo once; reads no client data):

- Structure: no `validate_construction` problems for the company; the fourteen compositions and eleven paths exist;
  every path step has a transition (the two shared macro records s56 and s03 are used as given), every uncalibrated
  step a sign and an "unknown" magnitude; the parallel responses of one LPR move (corporate loans, mortgages through the
  5-year LPR, posted deposit rates, the bond curve, credit demand) are branches from the LPR, and the CGB, property and
  deposit-rate paths branch from their own drivers; the reduced forms (s27, s29, s58, s28, s30, s31) are never steps of
  the structural paths they summarize, and each names its path.
- Financial integrity: every part of a driving view has a fixed-weight accounting link (the two reconciling segment views have none) equal to its native sd over
  the total's; one unit per view; the views that leave something out keep a residual; the priors of every additive view
  reconcile within 0.5% (exactly); the segment views share no part with the driven views and no causal link enters
  them; FVOCI marks reach CET1 and never profit; capital is a stock with signed flows, not an additive view.
- A Chinese state bank's economics: loans reprice off two LPR tenors and deposits lag through maturities (no direct LPR
  → deposit-cost link); deposit-rate cuts carry their counter-paths (agency fees up, prepayment up, savers terming out
  under a `state:` tag); falling yields reach income, gains and capital separately, with below-book reinvestment under a
  `state:` tag; property reaches impairment through mortgage and developer NPLs and through the IFRS 9 outlook, with the
  coverage buffer as a counter-path; the fiscal mortgage subsidy reaches asset quality and has no link to the bank's
  loan yield or NIM; a state injection adds to CET1.
- Calibration: no new link carries a size (nothing in the material supports one); s27–s31 and s58 keep their sizes with
  magnitude "assumption" and named unresolved inputs; the NII → share price link is written out, uncalibrated, so the
  taxonomy default does not add an unevidenced size; at least 25 identity, stock-flow, matrix and state steps carry
  their conversion tag and stay uncalibrated; every missing input says whether the supplied material was searched (no
  `not_yet_reviewed` remains).
- Generalization: a slowdown in Chinese growth, for which no CCB path was written, traced through every link (below).
- Delivery: compositions in `financial_bridge`, named paths as `business_construction` transmission paths, accounting
  links as `accounting_identity`, uncalibrated links as `represented_uncalibrated` with their sign, s27's transition in
  the export; new node ids returned by `/v1/world-models/sally_demo/graph`, the construction and trace endpoints.

Sally's expected paths (`tests/scenario/test_sally_expected_paths.py`, S-T4 reads this bank) still pass: the three
existing values keep their ids and priors, s27–s31 and s58 keep their sizes and signs, and no new link is calibrated, so
the thesis's outputs and must-channels are unchanged.

**Generalization trace (China growth slowdown).** `trace(g, "china_economy.gdp_growth", "china_construction_bank")`:
51 routes, 49 reach a financial endpoint, 6 calibrated end to end, all through Sally's records: growth → PBoC easing →
LPR → NIM → net profit (s02, s27, s29); growth → CGB yields → NIM (s57, s58, s29, and via s56); growth → easing →
property → NPL ratio → net profit (s02, s04, s28, s30); growth → easing → credit → net profit (s02, s03, s31, and via
s04, s77). Represented with sign but no size: easing → corporate loan yields, the 5-year LPR and mortgage yields,
posted deposit cuts (→ deposit cost, migration with agency fees, prepayment, the time-deposit mix), the bond curve
(→ new-purchase and book yields, FVOCI marks into CET1, trading gains), credit demand (→ corporate and personal loans
→ interest income and RWA), property (→ mortgage and developer NPLs, the IFRS 9 outlook, write-offs, the coverage
buffer); and activity → card and settlement fees, a branch no path holds. Routes end at net profit (8), interest income
(12), loan impairment (10), loans (6), fees (5), interest expense (3), CET1 capital (2), operating income (2) and earning
assets (1): the trace stops at the first composition total of each structural route (it follows causal links, and the
totals lead on only through accounting links). The only route that stops short of an endpoint ends at the share price
(nothing leads on from it). The trace reaches the bank through every business: rates, deposits, bonds, credit, fees
and capital.

## Completion report

Outcomes map to the release outcomes: built and verified (**BV**), built but uncalibrated (**BU**), blocked by a named
input (**BL**), not built (**NB**).

| # | Outcome | What is in the model now | What remains |
|---|---|---|---|
| G01 | BV | Line view, P&L bridge to profit before tax and net profit, NII by earning asset and funding source, fees, credit impairment, loans by type, earning assets; 39 accounting links with sd-ratio weights | — |
| G02 | BV | Basis and metric on the three existing values (`operating_profit` is metric `net_profit`) and on every new one | — |
| G03 | BL | s27, s29 scoped as reduced forms of `ccb.path.lpr_nii`, magnitude "assumption" | an NII or NIM sensitivity to an LPR cut, or a repricing gap by tenor (not disclosed in the reviewed sources) |
| G04 | BU | `ccb.path.lpr_nii` with five parallel branches into the NII accounts; `pboc.loan_prime_rate_5y` | LPR-priced share and reset dates, mortgage reset terms, deposit maturity profile, balances and yields by type |
| G05 | BU | `ccb.path.deposit_repricing` with migration, agency-fee, prepayment and mix counter-paths | deposit cost by type, migration volumes, prepayment rate |
| G06 | BU | `ccb.path.cgb_yields`, `ccb.path.securities_reinvestment`; s58 scoped | book yield, maturities, new-purchase yields, FVOCI holdings and duration |
| G07 | BU | `ccb.path.property_credit`; s28, s30 scoped | mortgage and developer NPL ratios, ECL scenarios, coverage floor |
| G08 | BU | `china_economy.mortgage_interest_subsidy`, `ccb.path.mortgage_subsidy`; `capital_injection`, `ccb.path.state_capital` | eligible volume; the bank's share of the injection |
| G09 | BU | `ccb.path.credit_growth`, `ccb.comp.loans_by_type`; s31 scoped | the bank's loan growth by type; risk weights |
| G10 | BU | `ccb.comp.fees`, `ccb.path.wealth_fees`, activity-fee links | fee lines; fee-cap rates |
| G11 | BU | capital values, `ccb.comp.capital_sources_uses`, three capital paths | CET1 capital and RWA in RMB; the bank's surcharge and TLAC need |
| G12 | BV (structure; undriven) | segment operating income and profit before tax views | segment drivers: the drivers act on lines that cut across segments |
| G13 | NB | operating expenses held as an undriven part of the P&L bridge | a cost driver |
| G14 | BV | NII → share price written out, uncalibrated | — |
| G15 | BV | objects present in the v4.1.4 export | — |
| G16 | BV | node ids served by the query, construction and trace endpoints | — |
| G17 | BL | net profit, dividends, payout and CET1 ratio bound as dated baselines; mortgage share cited | a company workbook or report (no view reconciles at baselines: below) |
| G18 | NB | — | overseas assets and income; nothing in the supplied material |

Counts: 18 gaps. By category (a gap can carry two): MC 12, CAL 4, MAP 3, EXP 1, RET 1. By outcome: BV 6 (G01, G02, G12,
G14, G15, G16), BU 8 (G04–G11), BL 2 (G03, G17), NB 2 (G13, G18).

**Links.** 101 links touch the bank's values: 39 accounting (fixed weights), 8 calibrated causal (s27–s31, s58, s61
and the kind-default net profit → share price), 54 uncalibrated (mechanism and sign; two more new uncalibrated links sit
between macro values: LPR → 5-year LPR and subsidy → property sales). 99 carry a transition (not s61 or the kind
default). No new link is calibrated: the supplied material holds no sensitivity, scenario disclosure or supported
estimate for any of them.

**Reconciliation.** At the priors (medians), every one of the thirteen additive views adds up exactly (0.0%):
`check.py --reconcile --statistic median` reports 0 flags. At the baselines, none can be checked: the supplied
material holds net profit, dividends and the CET1 ratio, but no view's parts (no company workbook; the vendor's
revenue line is gross interest plus non-interest income, and its pre-tax line is not IFRS profit before tax), so
`--reconcile --baselines` flags all thirteen as missing levels and no unexplained difference can be computed (local
`reconciliation.md`). Units are one per view (tested).

**Sources and citations.** `check.py --sources <local construction folder>`: 7 source ids resolve, 0 do not; 97 links
and 6 values are cited (page and paragraph or chart, with the passage); 0 material claims without a citation.

**Inputs by status** (29 distinct inputs named in transitions, after `scripts/construction/inputs.py` searched the 11
supplied files, the six China Construction Bank PDFs and the five spreadsheets, for each): 7 found and connected (bound
as a baseline or a citation: CET1 ratio, payout, mortgage share, posted deposit cuts, fee caps
qualitatively, RWA density qualitatively, the state injection event; the LPR tenor history is also bound, on the macro link LPR → 5-year LPR), 3 found but not connected (NIM and credit cost
in charts whose bank values do not survive parsing; the requirement as a sector range only), 19 not disclosed in the
reviewed sources (each with the sources and corpus queries searched; where only system or sector figures were found,
the note says so), 0 not yet reviewed.

**Forecast coverage (Sally's thesis S-T4, an LPR cut with a property recovery).** It reaches the bank through 8
quantified links (s27, s29, s28, s30, s31, s58, s61 and the net profit → share price default) and excludes 20
uncalibrated ones (the LPR, deposit, bond, credit-growth, property, fee and capital steps, each with its sign). The
share of routes fully quantified is 23% to NIM, 33% to the NPL ratio and 33% to net profit; 20 inputs block a size
(13 not disclosed, 6 found and connected, 1 found but not connected).

**Calculation coverage by path.** "Calculated" contributes a size; accounting links carry it to the endpoint at fixed
weights; uncalibrated steps carry a sign only and are listed as unquantified by any forecast that reaches them.

| Path | Calculated (calibrated causal) | Accounting | Excluded: uncalibrated, with sign | Inputs blocking a size (status) |
|---|---|---|---|---|
| `ccb.path.lpr_nii` | s56, s03 (shared macro steps only); s27 and s29 are the reduced forms beside the path | 8 | `ccb-c-lpr-corpyield` (+), `ccb-c-lpr-lpr5y` (+), `ccb-c-lpr-listrate` (+), `ccb-c-lpr5y-mortyield` (+), `ccb-c-listrate-depcost` (+), `ccb-c-cgb-npy` (+), `ccb-c-npy-invyield` (+), `ccb-c-credit-corploans` (+), `ccb-c-corpyield-loanii` (+), `ccb-c-mortyield-loanii` (+), `ccb-c-depcost-depexp` (−), `ccb-c-invyield-invii` (+), `ccb-c-corploans-loanii` (+), `ccb-c-nii-nim` (+) | NII sensitivity, LPR-priced share and reset dates, mortgage reset terms, deposit maturity profile, balances and yields, book yield, loan growth by type (not disclosed); NIM history (found, not connected); posted deposit cuts, LPR tenor history (found, connected) |
| `ccb.path.deposit_repricing` | none | 9 | `ccb-c-listrate-depcost` (+), `ccb-c-listrate-deposits` (+), `ccb-c-listrate-agency` (−), `ccb-c-listrate-prepay` (−), `ccb-c-listrate-timeshare` (−), `ccb-c-timeshare-depcost` (+), `ccb-c-depcost-depexp` (−), `ccb-c-deposits-depexp` (−), `ccb-c-prepay-mortgages` (−), `ccb-c-mortgages-loanii` (+) | agency fees by product, deposit balances and cost, loan balances and yields, deposit maturity profile, migration volumes, prepayment rate (not disclosed); mortgage share, fee caps (found, connected) |
| `ccb.path.cgb_yields` | none; s58 is the reduced form beside it | 6 | `ccb-c-cgb-npy` (+), `ccb-c-cgb-fvoci` (−), `ccb-c-cgb-trading` (−), `ccb-c-npy-invyield` (+), `ccb-c-invyield-invii` (+), `ccb-c-fvoci-cet1` (+), `ccb-c-np-cet1` (+), `ccb-c-cet1cap-ratio` (+) | FVOCI holdings and duration, book yield and maturities, trading gains (not disclosed); CET1 ratio (found, connected) |
| `ccb.path.securities_reinvestment` | none | 5 | `ccb-c-maturities-invyield` (−), `ccb-c-invyield-invii` (+), `ccb-c-np-cet1` (+) | book yield, maturities, new-purchase yields (not disclosed); CET1 ratio (found, connected) |
| `ccb.path.property_credit` | none; s28 and s30 are the reduced forms beside it | 9 | `ccb-c-prop-mortnpl` (−), `ccb-c-prop-devnpl` (−), `ccb-c-prop-mortgages` (+), `ccb-c-prop-allowance` (+), `ccb-c-mortnpl-npl` (+), `ccb-c-devnpl-npl` (+), `ccb-c-npl-writeoffs` (−), `ccb-c-npl-allowance` (−), `ccb-c-npl-coverage` (−), `ccb-c-coverage-allowance` (+), `ccb-c-mortgages-loanii` (+) | ECL scenarios, developer and mortgage NPL ratios, coverage and floor, prepayment rate, loan yields (not disclosed); credit cost (found, not connected); mortgage share (found, connected) |
| `ccb.path.mortgage_subsidy` | none | 9 | `ccb-c-subsidy-mortnpl` (−), `ccb-c-subsidy-propsales` (+), `ccb-c-prop-mortgages` (+), `ccb-c-mortnpl-npl` (+), `ccb-c-npl-allowance` (−), `ccb-c-npl-writeoffs` (−), `ccb-c-mortgages-loanii` (+) | eligible volume, mortgage NPL ratio, coverage, prepayment, loan yields (not disclosed); credit cost (found, not connected); mortgage share (found, connected) |
| `ccb.path.credit_growth` | none; s31 is the reduced form beside it | 7 | `ccb-c-credit-corploans` (+), `ccb-c-credit-otherpers` (+), `ccb-c-corploans-corpyield` (−), `ccb-c-corploans-loanii` (+), `ccb-c-otherpers-loanii` (+), `ccb-c-corpyield-loanii` (+), `ccb-c-loans-rwa` (+), `ccb-c-rwa-ratio` (−) | loan growth by type, loan balances and yields (not disclosed); risk weights qualitatively, CET1 ratio (found, connected) |
| `ccb.path.wealth_fees` | none | 4 | `ccb-c-equity-agency` (+) | agency fees by product (not disclosed); fee caps (found, connected) |
| `ccb.path.capital_payout` | none | 0 | `ccb-c-np-cet1` (+), `ccb-c-np-dividends` (+), `ccb-c-dividends-cet1` (−), `ccb-c-cet1cap-ratio` (+) | CET1 ratio, payout (found, connected); every step is a stock-flow or ratio identity |
| `ccb.path.state_capital` | none | 0 | `ccb-c-injection-cet1` (+), `ccb-c-cet1cap-ratio` (+) | injection event and CET1 ratio (found, connected); the bank's share of the injection is not stated |
| `ccb.path.capital_requirements` | none | 0 | `ccb-c-req-payout` (−), `ccb-c-payout-dividends` (+), `ccb-c-dividends-cet1` (−), `ccb-c-cet1cap-ratio` (+) | requirement (found, not connected: sector range); payout, CET1 ratio (found, connected) |
| Generalization (China growth) | s02, s03, s04, s56, s57, s77 (shared macro links), then s27, s28, s29, s30, s31, s58 | the line and P&L views where a route crosses them | every structural rate, deposit, bond, credit, property, fee and capital step | as for the paths above |

**What a downstream agent can now trace or calculate.** Operating income as NII plus fees plus other income, and on to
profit before tax and net profit through operating expenses and credit impairment; the same totals by reporting
segment (reconciled, not driven); NII by earning asset and funding source; fees by product; loan impairment as
write-offs plus allowance build; loans by type and interest-earning assets (the NIM denominator); a calculated size
only along Sally's statistical records (LPR → NIM → net profit, CGB → NIM, property → NPL ratio → net profit, credit
growth → net profit), each now scoped as the reduced form of a named path; and, as signed mechanisms with conditions,
timing, evidence and breakers: repricing off two LPR tenors, posted deposit cuts and their slow pass-through,
deposit migration with agency fees, mortgage prepayment, the time-deposit mix, bond reinvestment below book yields,
FVOCI marks into CET1, trading gains, mortgage and developer asset quality, the IFRS 9 outlook and the coverage
buffer, the fiscal mortgage subsidy, policy-directed lending at thin spreads, RWA growth, payout, requirements and
state capital.

**What remains unsupported.** Any size on the structural paths (no sensitivity, gap table, balances, yields or NPL
splits in the supplied material, and most steps are products, ratios or accumulations); the magnitude of an LPR cut's
NII effect beyond Sally's assumed record; segment drivers; operating expenses; overseas operations and FX;
reconciliation at actual levels; the policy substitution between a fiscal subsidy and further LPR cuts.

## Conversion to the new method forms (Oct 18, second round)

The method gained identities (product, ratio, difference, weighted average), stocks and flows, one driving view per
total, state-dependent responses, calendar timing and new input statuses. This build was converted; the sections above
describe the converted model, and the first-round counts in the completion report are kept for comparison.

**Driving view per total.**

| Total | Driving view | Reconciling view (`drives: false`) | Why |
|---|---|---|---|
| `operating_income` | `ccb.comp.operating_income_by_line` | `ccb.comp.operating_income_by_segment` | the drivers (LPR, deposits, bonds, fees) act on lines that cut across segments; the segment parts have no link into the total |
| `profit_before_tax` | `ccb.comp.pretax` (the P&L bridge) | `ccb.comp.pbt_by_segment` | the bridge carries operating income, expenses and credit impairment; segment profit is reported, not driven |

No matrix was declared: no supplied source gives segment-by-line cells. Both reconciling views still reconcile at the
priors (`--reconcile`).

**Links converted by form** (33 tagged steps):

| Form | Object | Links | Unit algebra |
|---|---|---|---|
| product | `ccb.id.corporate_loan_income` (new value: interest income on corporate loans) | `ccb-c-corploans-loanii`, `ccb-c-corpyield-loanii` | CNY bn/yr = CNY bn x % x 0.01 |
| product | `ccb.id.mortgage_income` (new value) | `ccb-c-mortgages-loanii`, `ccb-c-mortyield-loanii` | as above |
| product | `ccb.id.deposit_interest` | `ccb-c-deposits-depexp`, `ccb-c-depcost-depexp` | negative expense: coefficient -0.01 |
| product | `ccb.id.investment_interest` | `ccb-c-invyield-invii`, new `ccb-c-fininv-invii` | as above |
| product | `ccb.id.dividends` | `ccb-c-np-dividends`, `ccb-c-payout-dividends` | % x CNY bn/yr x 0.01 (group profit stands in for attributable profit) |
| product | `ccb.id.nonperforming_loans` (new value) | new `ccb-c-npl-npls`, `ccb-c-loans-npls` | % x CNY bn x 0.01 |
| ratio | `ccb.id.nim` | `ccb-c-nii-nim`, `ccb-c-iea-nim` | % = CNY bn/yr / CNY bn x 100 |
| ratio | `ccb.id.cet1_ratio` | `ccb-c-cet1cap-ratio`, `ccb-c-rwa-ratio` | % = CNY bn / CNY bn x 100 |
| ratio | `ccb.id.provision_coverage` | `ccb-c-npl-coverage` (now from the NPL balance), new `ccb-c-reserve-coverage` | % = CNY bn / CNY bn x 100 |
| weighted average | `ccb.id.npl_ratio` | `ccb-c-mortnpl-npl`, `ccb-c-devnpl-npl`, new `ccb-c-othernpl-npl` | stated loan shares 0.2 / 0.04 / 0.76 (the synthetic construction mix) |
| stock-flow | `ccb.sf.cet1_capital` (365 days) | `ccb-c-np-cet1`, `ccb-c-injection-cet1` (in), `ccb-c-dividends-cet1` (out) | |
| stock-flow | `ccb.sf.mortgages` (365 days, period average) | `ccb-c-prepay-mortgages` (out) | originations and amortization are not flows here |
| stock-flow | `ccb.sf.loan_loss_reserve` (new value; 365 days) | new `ccb-c-allowance-reserve` (the build, held negative, as an outflow) | |
| state: threshold | | `ccb-c-coverage-allowance` (acts only above 150% coverage, the public floor), `ccb-c-req-payout` (acts only below a 10.5% CET1 ratio, the builder's assumption) | sizes unknown: uncalibrated |
| state: sign flip | | `ccb-c-maturities-invyield` (the stated sign below a 2.5% new-purchase yield, reversed above) | size unknown: uncalibrated |

Converted: 16 links to identities, 4 to stock-flows, 3 to state blocks (23). Not converted, each with its reason in
its note (10): `ccb-c-npy-invyield` (a rate that is its own lagged balance-weighted average),
`ccb-c-timeshare-depcost` (weights that are values), `ccb-c-deposits-oea` (needs a funding view), `ccb-c-fvoci-cet1` (a
stock's change into a stock), `ccb-c-npl-writeoffs` (a management disposal decision), `ccb-c-otherpers-loanii` (no
yield value for the residual portfolios), `ccb-c-loans-rwa` (RWA is not loans times one weight), and three state
conditions no value holds (`ccb-c-listrate-timeshare`, `ccb-c-cgb-trading`, `ccb-c-corploans-corpyield`). Calendar
repricing is recorded on `ccb-c-lpr5y-mortyield` (`timing.calendar`); the kernel does not schedule it. The synthetic
priors were reset so every identity holds at its construction levels (yields, deposits, the bond book, earning assets,
CET1 capital and dividends moved; new values: three loan-income lines, other-portfolio NPL ratio, NPL balance, loan loss
reserve).

**Links, before and after** (links touching the bank's values):

| | Before | After |
|---|---|---|
| Total | 101 | 102 |
| Accounting | 39 | 34 (segment views now reconcile, no links; a loan-income view added) |
| Identity | 0 | 21 |
| Stock-flow | 0 | 5 |
| Calibrated causal | 8 (Sally's records, s61, the kind default) | 8 (unchanged) |
| Uncalibrated | 54 | 34 (3 of them carry a state block) |

**Calibration.** No new size from evidence: the supplied material holds no disclosed scenario, sensitivity or
named-peer size for any link (`--disclosure`, `--side` and `peer` have nothing to work on). The new statuses replace
blanket "not disclosed": inputs are now 7 found and connected, 2 found but not connected, 4 found as a proxy (sector or
system figures: developer NPLs, loan growth by type, deposit migration, the capital requirement), 12 disclosed in the
bank's annual report but not supplied, 4 not disclosed, 0 not yet reviewed.

**Reconciliation now.** At the priors (medians): 14 additive views and 10 identities, all within 0.5% (NIM 0.01%, the
rest exact); 0 flags. At the baselines: 14 views and 9 identities blocked by missing levels (not a discrepancy); the
dividends identity checks against the FY2025 actuals (0.06%, but the payout baseline is derived from the same two
actuals, so this is a consistency check, not evidence). No stock-flow roll-forward can be checked: CET1 capital,
mortgages and the reserve have no dated levels in the supplied material. `bundles.py check` passes on the baselines.

**Coverage now.** S-T4 (an LPR cut with a property recovery) reaches the bank through 14 quantified links (was 8): the
six of Sally's records, s61, the kind default, and six exact steps (NPL ratio to NPL balance to coverage, net profit to
dividends and CET1 capital, CET1 to the ratio); 18 uncalibrated links are excluded (was 20). Share of routes fully
quantified: NIM 30% (was 23%), NPL ratio 33%, net profit 35% (was 33%). Own steps against summary links: every
quantified route to NIM and to the NPL ratio runs through Sally's summary links only; to net profit, 8 of 12 quantified
routes use own steps (the exact capital and dividend steps), and 2 of 26 own steps on those routes are quantified.
Blocking inputs (bank-specific): 9 disclosed but not supplied, 4 found and connected, 2 proxies, 2 not disclosed, 1
found but not connected.

The China growth trace (through totals): 329 routes, 295 reach an endpoint, 42 fully calibrated (was 6); calibrated
routes now continue from net profit into CET1 capital, dividends and the CET1 ratio. It stops at the share price and,
at the depth bound, at the allowance build.

**Calculation coverage by path (after).**

| Path | Calibrated causal | Exact (identity / stock-flow) | Accounting | Excluded: uncalibrated, with sign | Inputs blocking a size (status) |
|---|---|---|---|---|---|
| `ccb.path.capital_payout` | none | `ccb-c-np-cet1`, `ccb-c-np-dividends`, `ccb-c-dividends-cet1`, `ccb-c-cet1cap-ratio` | 0 | none | none named |
| `ccb.path.capital_requirements` | none | `ccb-c-payout-dividends`, `ccb-c-dividends-cet1`, `ccb-c-cet1cap-ratio` | 0 | `ccb-c-req-payout` (-) | dividend payout ratio policy (found, connected); CET1 requirement incl. systemic surcharge and TLAC (proxy) |
| `ccb.path.cgb_yields` | none | `ccb-c-invyield-invii`, `ccb-c-np-cet1`, `ccb-c-cet1cap-ratio` | 6 | `ccb-c-cgb-npy` (+), `ccb-c-cgb-fvoci` (-), `ccb-c-cgb-trading` (-), `ccb-c-npy-invyield` (+), `ccb-c-fvoci-cet1` (+) | FVOCI bond holdings and their duration, financial investments: book yield, maturities and new-purchase yields, net trading and investment gains (disclosed, not supplied); CET1 capital and ratio (found, connected) |
| `ccb.path.credit_growth` | none | `ccb-c-corploans-loanii`, `ccb-c-corpyield-loanii`, `ccb-c-rwa-ratio` | 9 | `ccb-c-credit-corploans` (+), `ccb-c-credit-otherpers` (+), `ccb-c-corploans-corpyield` (-), `ccb-c-otherpers-loanii` (+), `ccb-c-loans-rwa` (+) | average loan balances and yields by type (disclosed, not supplied); risk weights by portfolio (RWA density) (found, connected); loan growth by type (proxy) |
| `ccb.path.deposit_repricing` | none | `ccb-c-depcost-depexp`, `ccb-c-deposits-depexp`, `ccb-c-prepay-mortgages`, `ccb-c-mortgages-loanii` | 10 | `ccb-c-listrate-depcost` (+), `ccb-c-listrate-deposits` (+), `ccb-c-listrate-agency` (-), `ccb-c-listrate-prepay` (-), `ccb-c-listrate-timeshare` (-), `ccb-c-timeshare-depcost` (+) | agency fee income by product (funds, bancassurance, wealth management products), average deposit balances and cost (demand versus time), deposit maturity profile (time deposits by remaining tenor) (disclosed, not supplied); regulatory fee-rate caps (bancassurance, fund distribution) (found, connected); mortgage prepayment rate (not disclosed); deposit migration to wealth management products (volumes) (proxy) |
| `ccb.path.lpr_nii` | `s56`, `s03` | `ccb-c-corpyield-loanii`, `ccb-c-mortyield-loanii`, `ccb-c-depcost-depexp`, `ccb-c-invyield-invii`, `ccb-c-corploans-loanii`, `ccb-c-nii-nim` | 10 | `ccb-c-lpr-corpyield` (+), `ccb-c-lpr-lpr5y` (+), `ccb-c-lpr-listrate` (+), `ccb-c-lpr5y-mortyield` (+), `ccb-c-listrate-depcost` (+), `ccb-c-cgb-npy` (+), `ccb-c-npy-invyield` (+), `ccb-c-credit-corploans` (+) | NII sensitivity to an LPR cut (repricing gap by tenor), average deposit balances and cost (demand versus time), deposit maturity profile (time deposits by remaining tenor), financial investments: book yield, maturities and new-purchase yields (disclosed, not supplied); posted deposit rate cuts and their effective dates, the spread between the 1-year and 5-year LPR moves (found, connected); mortgage repricing date and spread over the 5-year LPR, share of corporate loans priced off the LPR and their repricing dates (not disclosed); loan growth by type (proxy) |
| `ccb.path.mortgage_subsidy` | none | `ccb-c-mortnpl-npl`, `ccb-c-mortgages-loanii` | 10 | `ccb-c-subsidy-mortnpl` (-), `ccb-c-subsidy-propsales` (+), `ccb-c-prop-mortgages` (+), `ccb-c-npl-allowance` (-), `ccb-c-npl-writeoffs` (-) | provision coverage ratio and the regulatory floor (disclosed, not supplied); mortgage share of total loans (found, connected); credit cost (impairment over loans) (found, not connected); eligible first-home mortgage volume under the subsidy, mortgage prepayment rate (not disclosed) |
| `ccb.path.property_credit` | none | `ccb-c-mortnpl-npl`, `ccb-c-devnpl-npl`, `ccb-c-npl-npls`, `ccb-c-npl-coverage`, `ccb-c-allowance-reserve`, `ccb-c-reserve-coverage`, `ccb-c-mortgages-loanii` | 10 | `ccb-c-prop-mortnpl` (-), `ccb-c-prop-devnpl` (-), `ccb-c-prop-mortgages` (+), `ccb-c-prop-allowance` (+), `ccb-c-npl-writeoffs` (-), `ccb-c-npl-allowance` (-), `ccb-c-coverage-allowance` (+) | ECL scenario weights and macro assumptions (house prices, sales), mortgage NPL ratio, provision coverage ratio and the regulatory floor (disclosed, not supplied); mortgage share of total loans (found, connected); credit cost (impairment over loans) (found, not connected); mortgage prepayment rate (not disclosed); developer loan NPL ratio and real estate exposure (proxy) |
| `ccb.path.securities_reinvestment` | none | `ccb-c-invyield-invii`, `ccb-c-np-cet1` | 5 | `ccb-c-maturities-invyield` (-) | financial investments: book yield, maturities and new-purchase yields (disclosed, not supplied) |
| `ccb.path.state_capital` | none | `ccb-c-injection-cet1`, `ccb-c-cet1cap-ratio` | 0 | none | none named |
| `ccb.path.wealth_fees` | none | none | 4 | `ccb-c-equity-agency` (+) | agency fee income by product (funds, bancassurance, wealth management products) (disclosed, not supplied); regulatory fee-rate caps (bancassurance, fund distribution) (found, connected) |

**What still cannot be expressed after the conversion.**

1. **A rate's own roll-forward.** The book yield moves toward new-purchase yields at the pace of maturities: a
   balance-weighted average of cohorts. Neither a stock-flow (it takes flows into a stock) nor a weighted average
   (stated weights) holds it, so `ccb-c-npy-invyield` and the reinvestment drag stay sign-only.
2. **Weights that are values.** Deposit cost is a mix-weighted average whose weight (the time-deposit share) moves; the
   group NPL ratio's loan mix is held as constant stated shares. A sum of products would need each product as an
   identity plus a composition, and the model holds no time and demand deposit rates.
3. **A reduced form beside an exact identity.** NIM is now exactly NII over earning assets, and s29 (NIM to net profit)
   is Sally's statistical record. As soon as a quantified route moves NII, net profit receives it twice: through the
   accounts and through NIM and s29. Nothing in the S-T4 thesis moves NII today, so outputs are unchanged, but the
   method has no way to mark a statistical link as superseded by a structural route without retiring it.
4. **States on conditions that are not values.** Whether savers expect further cuts, whether loan growth is
   policy-directed, whether management chooses to realize bond gains: a state block needs a value and a level.
5. **Calendar repricing** is recorded, not scheduled; **policy substitution** (a fiscal subsidy lowering the odds of an
   LPR cut) has no relation type; the **state as a joint decision-maker** (owner, regulator, central bank) remains
   separate threshold links.
6. **No baselines for the roll-forwards.** Every stock-flow and most identities are blocked at the baselines; the
   bank's annual report (disclosed, not supplied) would unblock them.

## What the method could not express for this bank

The method carried over from JPMorgan (gap register, compositions, transitions, paths, counter-paths, evidence,
generalization trace), and the same limits recur (products of two states, ratios, stock-flows, matrix views; see
[JPMorgan](jpmorgan.md#what-the-method-could-not-express-for-a-bank)); 33 links here carry a conversion tag for them.
What is new for a Chinese state bank:

1. **Administered prices, not market betas.** Loans reprice off a benchmark that the PBoC guides and the panel banks
   quote; deposits reprice when the large banks cut posted rates together, by coordination and with a lag that has
   ranged from a year to the same quarter. The decision (whether and when deposit rates follow) is a policy event, not
   a pass-through coefficient. A link has one kernel; the method needs an event-triggered link whose lag and size are
   set by a decision value, and a way to say "follows within one to four quarters, or not at all".
2. **Repricing by calendar.** Mortgages reset to the 5-year LPR on a fixed date (usually 1 January), so the same cut
   lands in NII at very different times depending on the month it happens. A kernel measured in days from the shock
   cannot express a calendar reset; the method needs a repricing schedule (a share of the book by reset date).
3. **Policy substitution.** A fiscally funded mortgage subsidy lessens the need for further LPR cuts: the subsidy should
   lower the probability of the next policy move, not the rate itself. The LPR is a decision variable, and a link into
   it would be read as a causal effect on the rate; the method has no "changes the odds of a decision" relation, so
   this is a description only.
4. **The state as shareholder and regulator at once.** Payout, injections and requirements are set by related parts of
   the state (the finance ministry as owner, the regulator, the PBoC), trading off dividends to the budget against
   capital for policy lending. The method holds them as separate signed links (`ccb-c-req-payout`,
   `ccb-c-injection-cet1`) with a `state:` threshold; it cannot hold a joint decision with an objective.
5. **Two LPR tenors from one decision variable.** Sally's world has the 1-year LPR as the decision; the 5-year tenor
   (the mortgage benchmark) was added as a value linked to it. Their spread is itself a policy choice (housing support
   through the 5-year tenor), so a forecast that cuts only the 1-year LPR moves mortgages through an uncalibrated link
   that ought to be a second decision.
6. **Sector evidence, not bank evidence.** The supplied research is about China's banks as a group (system credit,
   sector NPLs, Big Four fee pressure), with the bank's own figures mostly in charts whose values do not survive
   parsing. The input statuses cannot say "found for the sector, not for this bank": such inputs are recorded as not
   disclosed with a note. A status (or an evidence level) for peer or sector evidence would let a downstream agent use
   a sector figure as a labelled proxy.
7. **Notes do not reach the model.** The conversion tags live in the construction file; interaction notes are not
   loaded into the graph or exported, so a downstream agent sees the tagged links as plain uncalibrated links. The tests
   read the tags from the file.
8. **No baselines without a workbook.** With no company model, no additive view can be reconciled at actual levels;
   the reconciliation check can only report missing levels. A company's annual report tables (or a vendor's
   standardized bank template) would close this; a vendor's generic statement does not, because its lines (gross
   revenue, a non-IFRS pre-tax line) do not map to a bank's IFRS lines.
