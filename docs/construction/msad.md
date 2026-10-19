# MS&AD Insurance: business construction

<!-- toc -->
**Contents**

- [Gap register](#gap-register)
- [Audit before modifying](#audit-before-modifying)
- [Definitions and bases](#definitions-and-bases)
- [Readable view](#readable-view)
  - [Business composition](#business-composition)
  - [Identities](#identities)
  - [Stocks and flows](#stocks-and-flows)
  - [Matrix `msad.mx.domestic_nonlife`: msad.comp.domestic_nonlife_by_source x msad.comp.domestic_nonlife_by_company (the rows drive the total; msad.comp.domestic_nonlife_by_company reconciles)](#matrix-msadmxdomesticnonlife-msadcompdomesticnonlifebysource-x-msadcompdomesticnonlifebycompany-the-rows-drive-the-total-msadcompdomesticnonlifebycompany-reconciles)
  - [Operating and financial paths](#operating-and-financial-paths)
- [Validation](#validation)
- [Completion report](#completion-report)
<!-- /toc -->

The construction lives in `data/worlds/sally_demo/construction/msad.yaml` (values, links with their transitions, named
paths, compositions) plus light edits to the `msad` entity and to s35–s40 and s71. It follows the Tokio Marine build
([tokio_marine.md](tokio_marine.md)), the direct peer, with MS&AD's own reporting: domestic non-life by company (Mitsui
Sumitomo, Aioi Nissay Dowa), international by business (MS Amlin, Asia, Americas, Europe, other), domestic life by
company (MSI Aioi Life, MSI Primary Life), group adjusted profit and its bridge to net income, and strategic-equity sale
gains held as their own part. This page is structure only: object ids, bases, categories, tests. The client-derived side
(passages, page and cell bindings, dated levels) stays local under `data/sally_data/construction/msad/` (`gap_evidence.md`,
`sources.json`, `citations.json`, `baselines.json`, `estimates.json`, `input_search*.{json,md}`, `reconciliation.md`,
`coverage.md`, and the full readable view with levels).

Source ids used in transitions (bindings are local): `msad.r1` broker note on Tokio Marine with a three-insurer
valuation table (the only MS&AD figures in the supplied material); `msad.r2` broker stock report on Tokio Marine with
a Japanese P&C market profile and sector outlook; `msad.macro` the client's yen-rates workbook (its company-mapping
rows); `msad.x1` an expert call on the US D&O market; `msad.peer` the Tokio Marine company-model workbook, read only for
the J-GAAP mechanics a Japanese P&C company reports (catastrophe-reserve provision and reversal, lines, income by asset
class), never for MS&AD figures; `msad.pub` public business and accounting knowledge of MS&AD's group structure and of
Japanese P&C accounting, not in the supplied material; `msad.corpus` the search scope (the whole supplied corpus).

**The supplied material holds no MS&AD company model, segment model, results release or company-specific broker note.**
Every MS&AD figure in it is one row of a peer valuation table and two sector statements. So the structure below comes
from MS&AD's public reporting (carried as `inferred`, not `documented`, because that reporting is not in the reviewed
material), every operating link is uncalibrated, and every level is a synthetic round prior.

## Gap register

Written before the model was changed. "Internal" is the loaded sally_demo graph and its YAML; "export" is the v4.1.4
pack the reviewer inspected (036, state version 432). Categories: **MC** missing construction, **CAL** missing
calibration, **MAP** incorrect mapping, **EXP** export omission, **RET** retrieval omission. Outcomes are in the
[completion report](#completion-report).

| # | Gap (missing or incorrect structure) | Present now (internal / export) | Add or correct | Evidence or input needed | Conclusions affected | Test that shows it done | Cat. |
|---|---|---|---|---|---|---|---|
| G01 | Group profit definition: `msad.operating_profit` is named group adjusted profit but exported as metric `operating_profit`; s39/s40 add two businesses with statistical weights (0.45, 0.40) and nothing else | Internal: no basis; s39, s40 causal "adds to". Export: REL_MS_AD_INSURANCE__E69_FIRM_FINANCIALS__OPERATING_PROFIT | `features.metric: group_adjusted_profit` and a basis; s39/s40 become accounting links on one basis with sd-ratio weights; add domestic life, financial services and an explicit other/consolidation residual | Company definition of group adjusted profit by business (public; not in the supplied material) | Any group-profit sum; international share; FX and rate effects on group profit | `test_adjusted_profit_view_reconciles`, `test_export_names_metrics_by_definition` | MAP |
| G02 | Group adjusted profit versus net income | Internal: no net income value. Export: none | `msad.comp.net_income_bridge`: net income = adjusted profit − catastrophe-reserve add-back + other, driven from adjusted profit (one direction, so nothing is counted twice) | Company reconciliation table (not in the supplied material) | Statutory EPS; payout on net income; why a catastrophe year hits adjusted profit harder than net income | `test_net_income_is_downstream_of_adjusted_profit` | MC |
| G03 | Domestic non-life by company (Mitsui Sumitomo, Aioi Nissay Dowa); the alias "Mitsui Sumitomo profit" sits on the group's domestic value | Internal: `msad.domestic_profit` one value. Export: E75_REINVESTMENT_INCOME__DOMESTIC_PROFIT | `msad.comp.domestic_nonlife_by_company` with a residual (other domestic companies and eliminations); move the alias to `msad.msi_profit` | Profit by company (not in the supplied material) | "MS&AD domestic" read as one company; Toyota-linked auto exposure at Aioi Nissay Dowa | `test_required_compositions_exist` | MC / MAP |
| G04 | Domestic non-life by source: underwriting, recurring investment income, strategic-equity sale gains | Internal: none | `msad.comp.domestic_nonlife_by_source`; gains are a separate, non-recurring part | Definition: whether group adjusted profit includes sale gains in the plan in force | Recurring versus one-off profit; how much cross-holding sales flatter adjusted profit | `test_sale_gains_are_a_separate_nonrecurring_part` | MC |
| G05 | Underwriting units: premiums by line; loss, expense and combined ratios | Internal: none | `msad.comp.dnl_premiums_by_line`, `msad.comp.combined_ratio` | Premiums and ratios by line (not in the supplied material) | Premium growth decomposition; auto share; claims inflation by line | `test_required_compositions_exist` | MC |
| G06 | Claims inflation and auto repricing | Internal: none | `msad.path.auto_repricing` with retention and expense counter-steps | Severity, rate revisions, retention (market-level statements only) | Domestic margin path | `test_required_paths_exist` | MC / CAL |
| G07 | Natural catastrophes, catastrophe reserves, reinsurance (domestic) | Internal: none | `msad.path.catastrophe_reserves`, with the J-GAAP reserve reversal as a state-dependent counter-path into net income only | Catastrophe budget, reserve balance and thresholds, reinsurance programme | Domestic profit and the adjusted/net gap in heavy years | `test_catastrophe_reserve_cushions_net_income_not_adjusted_profit` | MC / CAL |
| G08 | International by business (MS Amlin, Asia, Americas, Europe, other) and constant-FX versus translation | Internal: `msad.international_profit` with s35–s37 broad links. Export: E70_FX_TRANSLATION, E75_REINVESTMENT_INCOME__INTERNATIONAL_PROFIT | `msad.comp.international_by_business`, `msad.comp.international_by_source` at constant FX, accounting translation link | Profit by business, growth ex-FX | "Overseas is one exposure"; FX sensitivity | `test_international_constant_fx_and_translation_are_separate` | MC |
| G09 | International underwriting: Lloyd's and reinsurance catastrophes, US casualty reserves, the specialty rate cycle | Internal: none | `msad.path.international_underwriting`, `msad.path.us_casualty_reserves` | Catastrophe and reserve data by business | International margin | `test_required_paths_exist` | MC / CAL |
| G10 | Domestic life (MSI Aioi Life, MSI Primary Life) | Internal: none (no life value) | `msad.comp.domestic_life`; super-long JGBs into the protection book; US yields into foreign-currency annuity sales | Life profit by company; annuity sales | Rate sensitivity of the group beyond P&C | `test_required_compositions_exist`, path branches | MC / CAL |
| G11 | Investment income by asset class, the domestic bond portfolio, and reinvestment as six transitions | Internal: none (only s38: JGB 30Y → domestic profit). Export: shared PATH_..._JAPANESE_INSURERS_REINVESTMENT | `msad.comp.dnl_investment_income`, `msad.comp.dnl_assets_by_class`, `msad.path.reinvestment` | Maturity ladder, reinvestable cash, allocation, new-money yields | Every "higher yields help" conclusion | `test_reinvestment_has_its_six_transitions`, `test_no_invented_ladder` | MC / CAL |
| G12 | Broad yield links assume a market yield applies to a whole book (s36, s37, s38) | Internal: calibrated, no scope | Keep ids and sizes (Sally's expected paths); add transitions with scope, "assumption" magnitude and a never-add rule | Asset-level scope (G11) to recalibrate | JGB- and UST-driven upside | `test_broad_yield_links_state_their_scope` | MAP / CAL |
| G13 | FX hedge cost on foreign bonds | Internal: none | `msad.fx_hedge_cost` from the policy-rate gap into foreign-securities income | Hedge notional and ratio | Net benefit of foreign yields | path `msad.path.fx_hedge_cost` | MC / CAL |
| G14 | Asset marks and liability valuation reach equity and ESR, not recurring profit | Internal: none | `msad.path.asset_marks_liabilities` | ESR sensitivities by shock | Solvency and book-value effects of rate moves | `test_marks_never_reach_adjusted_profit` | MC / CAL |
| G15 | Cross-shareholding reduction: forgone dividends, sale gains, book, ESR, capital | Internal: none | `msad.path.cross_holding_disposal` | Sale programme, book, dividend yield of what is sold | Payout capacity; adjusted-profit quality | `test_cross_holding_sales_reach_profit_only_as_gains_and_forgone_dividends` | MC |
| G16 | Equity marks on strategic holdings; the sum-of-parts value a broker puts on them | Internal: s71 (equity index → share price) only | `msad.path.equity_marks` to equity, ESR and the per-share holding value | ESR equity sensitivity | Book value, ESR and valuation in an equity sell-off | `test_required_paths_exist` | MC / CAL |
| G17 | Overseas translation with its counter-effect (foreign-currency claims reserves in domestic non-life) | Internal: s35 only | `msad.path.overseas_translation`; reserve link uncalibrated (no MS&AD sensitivity in the material) | Company per-yen sensitivity | Net group FX sensitivity | `test_fx_counter_effect_is_represented_and_uncalibrated` | MC / CAL |
| G18 | Capital and shareholder return (ESR, excess capital, remittances, payout) | Internal: none | Values, `msad.path.capital_payout`, non-additive `msad.comp.capital_sources_uses` | Parent cash, remittances, payout policy | Dividend and buyback conclusions | `test_capital_is_a_stock_with_flows_not_an_additive_view` | MC / CAL |
| G19 | Growth execution (acquisitions and stakes) | Internal: none | `msad.path.growth_execution` | Deal terms | Inorganic growth | `test_required_paths_exist` | MC / CAL |
| G20 | Policy growth, including the dealer channel of the Toyota-affiliated auto insurer | Internal: none | `msad.path.policy_growth`; a Toyota unit-sales link into insured exposure | Exposure and channel data | Premium growth versus profit | `test_required_paths_exist` | MC / CAL |
| G21 | Local baselines: no MS&AD actuals for the new values | Internal: synthetic priors only | Bind what the material has (one per-share holding value; one EPS estimate kept apart); report the rest as blocked | An MS&AD company model or results release | Reconciliation at baselines; any calibration | `reconciliation.md` (local) | CAL |
| G22 | Transitions, compositions and named paths absent from the inspected export | Export: none for MS&AD | Carried in the export (relationship properties, `financial_bridge`, `business_construction` paths) | none | Downstream agent context | `test_new_objects_reach_the_export` | EXP |
| G23 | New node ids not retrievable through the service | Internal API: values not present | `/v1/world-models/sally_demo/graph`, `/construction/msad` serve them | none | Agent retrieval | `test_new_objects_reach_the_api` | RET |
| G24 | Shared insurer path in the export groups two insurers' parallel responses | Export: PATH_..._JAPANESE_INSURERS_REINVESTMENT | Do not touch; company paths beside it | none | Path resolution | business paths exported with `path_kind: business_construction` | EXP |
| G25 | Market-wide claim states (Japan P&C claim severity, US liability severity) are held on the `tokio_marine` entity | Internal: `tokio_marine.japan_claim_severity`, `tokio_marine.us_liability_severity` | Reused as shared drivers (no second id); moving them to a market entity is a shared-file change outside this build | none | Peer comparisons of claims inflation | `test_shared_drivers_are_reused_not_duplicated` | MAP |

## Audit before modifying

| Requirement or object | Class | Controlling object | Action |
|---|---|---|---|
| Identity, aliases, memberships, share price default (`msad`) | Already owned | entities.yaml `msad` | description scoped (yields reach only reinvested money); alias "Mitsui Sumitomo profit" moved to `msad.msi_profit` |
| Broad FX and yield links s35–s38, s71 | Already owned (statistical records) | interactions.yaml | ids and sizes kept; transitions added (Modify lightly) |
| s39, s40 aggregation | Modify lightly | interactions.yaml | accounting links on the group-adjusted-profit basis, weights from scales |
| `operating_profit`, `domestic_profit`, `international_profit` definitions | Modify lightly | entities.yaml | `features.view/basis/metric` added; ids kept for Sally's expected paths |
| Compositions, operating states, connected paths, bindings | Missing | construction/msad.yaml; local sources, citations, baselines | built |
| Shared macro values (JGB, UST, Bund yields, USD/JPY, policy rates, CPI, wages, GDP, TOPIX) | Already owned | entities.yaml | reused, never redefined; two new shared values added (Japan and US insured catastrophe losses) |
| Tokio Marine objects, the shared insurer export path, other companies' files | Do not touch | tokio_marine.yaml, export generator | untouched; two Tokio Marine market states read as drivers (G25) |

## Definitions and bases

- **Group adjusted profit by business** (`features.basis` "GAP" on `operating_profit` and its parts): the company's own
  definition, J-GAAP based. Parts: domestic non-life, international, domestic life, financial services and risk-related
  services, and a residual (holding company, equity-method and consolidation adjustments) that also absorbs the gap
  between the synthetic parts and the total. Exported metrics: `group_adjusted_profit`,
  `domestic_nonlife_adjusted_profit`, `international_adjusted_profit`, `domestic_life_adjusted_profit`, ...
- **Net income bridge**: net income = group adjusted profit − after-tax reserve add-back + other differences. It runs one
  way (adjusted profit → net income), so an operating change reaches net income through adjusted profit and is never
  counted twice. The add-back is the J-GAAP catastrophe and price-fluctuation reserve provision, which is why a heavy
  catastrophe year hits adjusted profit in full and net income less.
- **Strategic-equity sale gains** are a part of domestic non-life adjusted profit under the definition read here, held
  apart from recurring net interest and dividends. Whether the plan in force keeps them in adjusted profit is not
  established in the reviewed sources: it is an open input on `msad-a-dnl-xgain`; a definition that excludes them moves
  the part from the business view to the bridge.
- **Domestic non-life (J-GAAP DNL)**: the two P&C companies combined, as a matrix `msad.mx.domestic_nonlife`:
  by source (underwriting before catastrophe-reserve movements, recurring investment income, sale gains, taxes
  and other) drives domestic profit; by company (Mitsui Sumitomo, Aioi Nissay Dowa, other) reconciles (its links
  carry no size). No company × source cell is in the reviewed sources.
- **Underwriting identities** (J-GAAP DNL): loss ratio = 100 × net incurred losses / net premiums earned
  (`msad.id.loss_ratio`); expense ratio = 100 × underwriting expenses / net premiums written
  (`msad.id.expense_ratio`); underwriting profit = earned premium − incurred losses − expenses
  (`msad.id.uw_profit`). The combined ratio stays the sum of the two ratios (a reporting total with different
  denominators); drivers act on losses, earned premium and expenses, never on the ratios.
- **Investment income and assets** (J-GAAP DNL): premiums by line with compulsory auto as the residual; income
  by asset class with the credit to savings-type policies as its liability side; domestic bond income = 0.01 ×
  book value × book yield (`msad.id.bond_income`); assets by class. The domestic bond book, the strategic
  equity book and deployable capital are stocks (`msad.sf.*`). No maturity ladder, tenor, classification or
  hedge notional is represented.
- **International**: by business in yen (MS Amlin, Asia, Americas, Europe, other) and by source at constant FX
  (underwriting, investment income, taxes and other). The yen value is the constant-FX value times the reporting rates:
  `msad-a-intl-translate` carries the operating change, s35 the dollar rate. Sterling, euro and Asian rates are not
  carried.
- **Domestic life**: MSI Aioi Life (protection, long duration) and MSI Primary Life (bank-channel savings and
  foreign-currency annuities).
- **Shared drivers**: JGB, UST and Bund yields, USD/JPY, the policy rates, Japan CPI, wages and GDP, TOPIX, Toyota's Japan
  unit volume, and the market-wide claim states held on the `tokio_marine` entity (`japan_claim_severity`,
  `us_liability_severity`). Two new shared values: `japan_economy.nat_cat_insured_losses` and
  `us_economy.nat_cat_insured_losses` (industry insured catastrophe losses).
- **Converted forms (Oct 18)**: identities `msad.id.loss_ratio`, `msad.id.expense_ratio`, `msad.id.uw_profit`,
  `msad.id.bond_income`, `msad.id.adjusted_eps` (= 1000 × adjusted profit / shares); stock-flows
  `msad.sf.domestic_bonds` (purchases in, redemptions out), `msad.sf.cross_holding_book` (sales out),
  `msad.sf.excess_capital` (adjusted profit, sale proceeds and remittances in; shareholder returns and
  acquisitions out); the catastrophe-reserve reversal as a `state.threshold` (acts only above the catastrophe
  budget). Steps that fit no form keep a note starting "stays uncalibrated:" with the reason.

## Readable view

Generated by `uv run python scripts/construction/check.py sally_demo --entities msad` from the loaded model (the same
objects the API serves at `/v1/world-models/sally_demo/entities/msad/construction`). A `?` marks a step whose size is unknown
(uncalibrated). Levels are left out here; the local copy adds them.

133 links touch its values: 64 calibrated, 69 uncalibrated (represented, size unknown), 42 accounting, 11 identity, 8 stock-flow; 1 state-dependent; 132 carry a transition.

### Business composition

#### reporting segments: group adjusted profit by business, company definition (J-GAAP based) (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| MS&AD domestic P&C profit | `msad.domestic_profit` |
| MS&AD international business profit | `msad.international_profit` |
| MS&AD domestic life adjusted profit | `msad.domestic_life_profit` |
| MS&AD financial services and risk-related services adjusted profit | `msad.financial_services_profit` |
| Residual: MS&AD other and consolidation adjustments to group adjusted profit | `msad.adjusted_profit_residual` |
| **Total: MS&AD group adjusted profit** | `msad.operating_profit` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
The view every operating path feeds. Its residual absorbs the gap between the synthetic parts and total, and says so.

#### capital: sources and uses of deployable capital (not an additive partition; flows into a stock) (¥bn)

| Part | Value |
|---|---|
| MS&AD group adjusted profit | `msad.operating_profit` |
| MS&AD strategic equity sales | `msad.cross_holding_sales` |
| MS&AD dividends from overseas subsidiaries | `msad.overseas_remittances` |
| MS&AD shareholder returns | `msad.shareholder_returns` |
| MS&AD acquisition spend | `msad.acquisition_spend` |
| **Total: MS&AD deployable excess capital** | `msad.excess_capital` |

A non-additive view: its parts overlap.
Earnings capacity, parent cash, available capital and payout policy are related but distinct.

#### underwriting: combined ratio = loss ratio (E/I) + expense ratio (W/P), private insurance, both P&C companies (pct, fiscal year ending March)

| Part | Value |
|---|---|
| MS&AD domestic non-life loss ratio | `msad.dnl_loss_ratio` |
| MS&AD domestic non-life expense ratio | `msad.dnl_expense_ratio` |
| **Total: MS&AD domestic non-life combined ratio** | `msad.dnl_combined_ratio` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An identity of ratios with different denominators, not of amounts; no residual.

#### investment assets: J-GAAP investment assets by class, both P&C companies (balances) (¥bn)

| Part | Value |
|---|---|
| MS&AD domestic bond portfolio | `msad.dnl_domestic_bonds` |
| MS&AD strategic equity holdings | `msad.cross_holding_book` |
| MS&AD foreign securities holdings | `msad.dnl_foreign_securities` |
| Residual: MS&AD other investment assets | `msad.dnl_other_assets` |
| **Total: MS&AD domestic non-life investment assets** | `msad.dnl_investment_portfolio` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Balances by class only: no maturity ladder, tenor, classification or hedge notional is in the reviewed sources, so none is represented.

#### investment assets: J-GAAP net interest and dividends by asset class, both P&C companies (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| MS&AD dividends from domestic equities | `msad.dnl_div_domestic_equity` |
| MS&AD income from domestic bonds | `msad.dnl_inc_domestic_bonds` |
| MS&AD income from foreign securities | `msad.dnl_inc_foreign_securities` |
| MS&AD investment income credited to savings-type policies | `msad.dnl_deposit_credit` |
| Residual: MS&AD other interest and dividends | `msad.dnl_inv_residual` |
| **Total: MS&AD domestic non-life net interest and dividends** | `msad.dnl_investment_income` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Income by asset class; the credit to savings-type policies is the liability side (negative).

#### underwriting: J-GAAP net premiums written by line, both P&C companies (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| MS&AD domestic fire premiums | `msad.dnl_npw_fire` |
| MS&AD domestic voluntary auto premiums | `msad.dnl_npw_auto` |
| MS&AD domestic marine, personal accident and other premiums | `msad.dnl_npw_specialty` |
| Residual: MS&AD domestic compulsory auto liability premiums | `msad.dnl_npw_cali` |
| **Total: MS&AD domestic non-life net premiums written** | `msad.dnl_npw` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An activity measure, not profit; compulsory auto liability is a no-profit, no-loss line. The by-company split of lines (matrix) is not represented.

#### reporting segments: domestic life adjusted profit by company, company definition (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| MSI Aioi Life adjusted profit | `msad.life_mail_profit` |
| MSI Primary Life adjusted profit | `msad.life_primary_profit` |
| Residual: MS&AD other domestic life items | `msad.life_residual` |
| **Total: MS&AD domestic life adjusted profit** | `msad.domestic_life_profit` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.

#### reporting segments: domestic non-life adjusted profit by company, company definition (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Mitsui Sumitomo Insurance adjusted profit | `msad.msi_profit` |
| Aioi Nissay Dowa Insurance adjusted profit | `msad.adi_profit` |
| Residual: MS&AD other domestic non-life companies and eliminations | `msad.dnl_other_companies` |
| **Total: MS&AD domestic P&C profit** | `msad.domestic_profit` |

A reconciling view: its parts are observed and reconciled against the total but carry nothing into it, so it can be imported alongside the driving view without counting a change twice.
Overlaps msad.comp.domestic_nonlife_by_source: the same total, never added together.

#### underwriting: domestic non-life adjusted profit by source: underwriting, recurring investment income, strategic-equity sale gains, less taxes and other (J-GAAP, both P&C companies) (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| MS&AD domestic non-life underwriting profit | `msad.dnl_underwriting_profit` |
| MS&AD domestic non-life net interest and dividends | `msad.dnl_investment_income` |
| MS&AD gains on sales of strategic equity holdings | `msad.dnl_xholding_gains` |
| Residual: MS&AD domestic non-life taxes and other items | `msad.dnl_taxes` |
| **Total: MS&AD domestic P&C profit** | `msad.domestic_profit` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Sale gains are their own non-recurring part. The view the operating paths drive.

#### regions: international adjusted profit by business, yen at reporting rates (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| MS Amlin adjusted profit | `msad.intl_amlin_profit` |
| MS&AD Asia adjusted profit | `msad.intl_asia_profit` |
| MS&AD Americas adjusted profit | `msad.intl_americas_profit` |
| MS&AD Europe (Aioi Nissay Dowa Europe) adjusted profit | `msad.intl_europe_profit` |
| Residual: MS&AD other international adjusted profit | `msad.intl_residual` |
| **Total: MS&AD international business profit** | `msad.international_profit` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Overseas is not one exposure: MS Amlin carries catastrophe and reserve swings, Asia is growth and equity-method stakes.

#### regions: international adjusted profit at constant FX: underwriting plus investment income, less taxes and other (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| MS&AD international underwriting profit | `msad.intl_underwriting_profit` |
| MS&AD international investment income | `msad.intl_investment_income` |
| Residual: MS&AD international taxes and other items | `msad.intl_taxes` |
| **Total: MS&AD international adjusted profit at constant FX** | `msad.intl_profit_cfx` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Translated into the yen value by msad-a-intl-translate (s35 carries the dollar rate).

#### reporting segments: net income = group adjusted profit - after-tax reserve add-back + other differences (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| MS&AD group adjusted profit | `msad.operating_profit` |
| MS&AD reserve add-back to net income | `msad.reserve_addback` |
| Residual: MS&AD other differences between net income and adjusted profit | `msad.net_income_bridge_residual` |
| **Total: MS&AD net income** | `msad.net_income` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Net income is downstream of adjusted profit, so an operating change is never counted twice; the reserve add-back subtracts (negative accounting link).

### Identities

Each weight is derived from the values' levels and scales at construction (sd of the target per sd of the term), never estimated.

| Identity | Formula | Terms (weight, sd/sd) | Unit check |
|---|---|---|---|
| `msad.id.adjusted_eps` (ratio) | MS&AD adjusted EPS = 1000 x MS&AD group adjusted profit / MS&AD shares outstanding | MS&AD group adjusted profit (numerator, +1.000); MS&AD shares outstanding (denominator, -0.200) | ¥ per share = 1000 x ¥bn / m shares |
| `msad.id.bond_income` (product) | MS&AD income from domestic bonds = 0.01 x MS&AD domestic bond portfolio x MS&AD domestic bond book yield | MS&AD domestic bond portfolio (factor, +0.300); MS&AD domestic bond book yield (factor, +1.000) | ¥bn/yr = ¥bn x pct x 0.01 |
| `msad.id.expense_ratio` (ratio) | MS&AD domestic non-life expense ratio = 100 x MS&AD domestic non-life underwriting expenses / MS&AD domestic non-life net premiums written | MS&AD domestic non-life underwriting expenses (numerator, +0.810); MS&AD domestic non-life net premiums written (denominator, -0.810) | pct = 100 x ¥bn / ¥bn (written basis: a different denominator from the loss ratio) |
| `msad.id.loss_ratio` (ratio) | MS&AD domestic non-life loss ratio = 100 x MS&AD domestic non-life net incurred losses / MS&AD domestic non-life net premiums earned | MS&AD domestic non-life net incurred losses (numerator, +0.960); MS&AD domestic non-life net premiums earned (denominator, -0.640) | pct = 100 x ¥bn / ¥bn (earned/incurred basis) |
| `msad.id.uw_profit` (difference) | MS&AD domestic non-life underwriting profit = MS&AD domestic non-life net premiums earned - MS&AD domestic non-life net incurred losses - MS&AD domestic non-life underwriting expenses | MS&AD domestic non-life net premiums earned (total, +0.714); MS&AD domestic non-life net incurred losses (deduction, -0.686); MS&AD domestic non-life underwriting expenses (deduction, -0.347) | unknown |

### Stocks and flows

A flow held one sd above its level adds its weight to the stock every period: the stock accumulates it.

| Stock-flow | Roll-forward | Flows (weight per period, sd/sd) |
|---|---|---|
| `msad.sf.cross_holding_book` | MS&AD strategic equity holdings (closing) = MS&AD strategic equity holdings (opening) - MS&AD strategic equity sales, per 365 days | MS&AD strategic equity sales (outflow, -0.267) |
| `msad.sf.domestic_bonds` | MS&AD domestic bond portfolio (closing) = MS&AD domestic bond portfolio (opening) + MS&AD domestic non-life new investments - MS&AD domestic bond redemptions, per 365 days | MS&AD domestic non-life new investments (inflow, +1.667); MS&AD domestic bond redemptions (outflow, -1.250) |
| `msad.sf.excess_capital` | MS&AD deployable excess capital (closing) = MS&AD deployable excess capital (opening) + MS&AD group adjusted profit + MS&AD strategic equity sales + MS&AD dividends from overseas subsidiaries - MS&AD shareholder returns - MS&AD acquisition spend, per 365 days | MS&AD group adjusted profit (inflow, +0.155); MS&AD strategic equity sales (inflow, +0.500); MS&AD dividends from overseas subsidiaries (inflow, +0.200); MS&AD shareholder returns (outflow, -0.400); MS&AD acquisition spend (outflow, -0.500) |

### Matrix `msad.mx.domestic_nonlife`: msad.comp.domestic_nonlife_by_source x msad.comp.domestic_nonlife_by_company (the rows drive the total; msad.comp.domestic_nonlife_by_company reconciles)

No cells are given: the views reconcile to the total only.

Each company has underwriting, investment income and sale gains; the by-source view drives domestic profit (every operating path feeds it), the by-company view reconciles. No cell (company x source) is in the reviewed sources, so none is represented.

### Operating and financial paths

#### MS&AD asset marks and liability valuation

**Trigger:** super-long JGB yields move. **Endpoint:** MS&AD economic solvency ratio.

JGB 30Y yield → [assets] MS&AD unrealized gains on bonds? → [liabilities] MS&AD insurance liabilities at market value? → [equity] MS&AD shareholders' equity? → [solvency] MS&AD economic solvency ratio? → MS&AD economic solvency ratio?  (? marks a step whose size is unknown)

Asset marks and liability valuation are parallel routes to net assets and the ESR; neither reaches adjusted profit.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [assets] `msad-c-jgb-bondmark` | Higher yields lower the market value of available-for-sale bonds; policy-reserve-matching and held-to-maturity bonds are not marked; recurring profit is unaffected (market) | bonds classified available-for-sale; duration of those holdings; observable: unrealized gains on bonds in net assets | onset immediate; build none; persists until yields reverse or bonds mature; recognized period end | inferred / inferred / unknown / inferred | classification at amortized cost; short duration | unrealized gains on bonds | unknown |
| 2 [liabilities] `msad-c-jgb-liability` | Higher discount rates lower the economic value of long-dated insurance liabilities (a parallel route to the asset mark; matching does not imply full offset) (economic solvency measurement) | liabilities at market-consistent rates on the ESR basis; J-GAAP reserves are not marked; observable: ESR interest-rate sensitivity | onset immediate; build none; persists until rates reverse; recognized solvency reporting | inferred / inferred / unknown / inferred | duration mismatch; extrapolation beyond the last liquid tenor | insurance liabilities at market value | unknown |
| 3 [equity] `msad-c-bondmark-equity` | Unrealized gains and losses on available-for-sale bonds move net assets (after tax), never adjusted profit (group accounts) | observable: valuation difference on available-for-sale securities | onset period end; build none; persists until reversal; recognized quarterly balance sheet | inferred / inferred / unknown / inferred | deferred tax absorbs part | shareholders' equity | unknown |
| 4 [solvency] `msad-c-bondmark-esr` | The asset mark moves economic capital; the liability mark moves it the other way (parallel) (economic solvency measurement) | observable: ESR and its rate sensitivity | onset immediate; build none; persists until reversal; recognized solvency reporting | inferred / inferred / unknown / inferred | duration matching | economic solvency ratio | unknown |
| 5 `msad-c-liability-esr` | A higher economic value of liabilities lowers economic capital and the solvency ratio (economic solvency measurement) | observable: ESR and its rate sensitivity | onset immediate; build none; persists until reversal; recognized solvency reporting | inferred / inferred / unknown / inferred | asset duration matching the liabilities | economic solvency ratio | unknown |

Unresolved inputs: ESR sensitivity to interest rates (disclosed not supplied); bond holdings by classification and duration (not disclosed in reviewed sources).

#### MS&AD claims inflation and auto repricing

**Trigger:** repair parts, labor and construction costs rise. **Endpoint:** MS&AD group adjusted profit.

Japan P&C claim severity → [losses] MS&AD domestic non-life net incurred losses? → [reserves] MS&AD domestic non-life net incurred losses? → MS&AD domestic non-life loss ratio → MS&AD domestic auto rate revision? → [retention] MS&AD domestic policy retention? → [premium] MS&AD domestic voluntary auto premiums? → MS&AD domestic voluntary auto premiums? → MS&AD domestic non-life net premiums written → MS&AD domestic non-life net premiums earned? → MS&AD domestic non-life loss ratio → MS&AD domestic non-life combined ratio → MS&AD domestic non-life underwriting profit → MS&AD domestic non-life underwriting profit → MS&AD domestic P&C profit → MS&AD group adjusted profit  (? marks a step whose size is unknown)

Claims costs raise incurred losses (current and open-claim reserves) and so the loss ratio first; auto rate revisions follow with a lag, retention pushes back, and the new rates earn through as earned premium, the loss ratio's denominator. Underwriting profit is earned premium less losses less expenses (msad.id.uw_profit).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [losses] `msad-c-severity-loss` | Higher cost per claim (repair parts, labor, construction) at unchanged premiums raises the loss ratio before rates catch up (repairers, contractors, claimants) | premiums not yet repriced; claim frequency unchanged; observable: average claim cost and loss ratio by line | onset 1-2 quarters; build until repriced; persists until rates catch up; recognized quarterly results | broker / broker / unknown / inferred | falling claim frequency; rate increases already earning through | net incurred losses | unknown |
| 2 [reserves] `msad-c-severity-reserves` | Open claims are re-estimated at higher costs, a reserve charge in incurred losses before any repricing (domestic reserving actuaries) | open claims with long settlement (bodily injury, property) were reserved at older cost levels; observable: prior-year reserve development; provision for outstanding claims | onset next reserve review; build 1-3 years (settlement pattern); persists one-off per review; recognized quarterly reserve reviews | inferred / inferred / unknown / unknown | reserve margins that absorb the change | net incurred losses | unknown |
| 3 `msad.id.loss_ratio:msad.dnl_incurred_losses` | MS&AD domestic non-life loss ratio = 100 x MS&AD domestic non-life net incurred losses / MS&AD domestic non-life net premiums earned: MS&AD domestic non-life net incurred losses is a numerator; weight derived at the construction levels | unknown | onset same period; build none; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | +0.96 sd/sd (identity) |
| 4 `msad-c-loss-autorate` | A deteriorating auto loss ratio leads to rate revisions at renewal (rate filings, reference loss-cost changes); in an oligopoly the three groups move together (domestic pricing and underwriting management) | pricing discretion: filings or reference loss-cost revisions; competitors move too; observable: announced auto rate revisions; renewal rate change | onset 1-2 years (filing cycle); build one renewal cycle; persists until the next review; recognized earned over the following year | broker / broker / unknown / unknown | competitors hold prices; regulatory limits on auto rates | auto rate change | unknown |
| 5 [retention] `msad-c-autorate-retention` | Customers facing higher renewal prices shop around or reduce cover (counter-path to repricing) (policyholders and agents) | competitors offer lower prices; switching is easy; observable: renewal retention; policy counts | onset at renewal; build one renewal cycle; persists while the price gap persists; recognized written premium at renewal | inferred / inferred / unknown / unknown | industry-wide rate increases; dealer and agency relationships | policy retention | unknown |
| 6 [premium] `msad-c-autorate-premium` | Higher renewal rates raise premium per retained auto policy (domestic non-life) | policies renew at the new rate; observable: premium per policy; auto premium growth | onset at renewal; build one renewal cycle; persists until repriced; recognized written at renewal, earned over the term | broker / broker / unknown / inferred | lost volume (retention) offsets the price | auto premiums written | unknown |
| 7 `msad-c-retention-npw` | Higher retention keeps more auto premium on the books at renewal (domestic agents and dealers) | observable: renewal retention; policy counts | onset at renewal; build one cycle; persists while retained; recognized written at renewal | inferred / inferred / unknown / unknown | retention bought with price cuts | auto premiums written | unknown |
| 8 `msad-a-npw-auto` | Voluntary auto premiums are the largest line of domestic net premiums written | unknown | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | domestic premiums written | +0.50 sd/sd (accounting) |
| 9 `msad-c-npw-earned` | Written premium is earned over the policy term; profit arrives only if the premium covers expected claims and expenses (domestic non-life) | price adequacy: combined ratio below 100%; observable: combined ratio on a matching earned/incurred basis | onset 1-2 quarters; build over the policy term; persists while priced adequately; recognized earned pro rata | inferred / inferred / unknown / inferred | inadequate pricing; claims arriving faster than premiums are repriced | net premiums earned | unknown |
| 10 `msad.id.loss_ratio:msad.dnl_npe` | MS&AD domestic non-life loss ratio = 100 x MS&AD domestic non-life net incurred losses / MS&AD domestic non-life net premiums earned: MS&AD domestic non-life net premiums earned is a denominator; weight derived at the construction levels | unknown | onset same period; build none; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | -0.64 sd/sd (identity) |
| 11 `msad-a-cr-loss` | The loss ratio (E/I) is one term of the combined ratio | the Japanese convention adds an earned-basis loss ratio to a written-basis expense ratio: an identity of ratios, not of amounts | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | combined ratio | +0.91 sd/sd (accounting) |
| 12 `msad.id.uw_profit:msad.dnl_incurred_losses` | MS&AD domestic non-life underwriting profit = MS&AD domestic non-life net premiums earned - MS&AD domestic non-life net incurred losses - MS&AD domestic non-life underwriting expenses: MS&AD domestic non-life net incurred losses is a deduction; weight derived at the construction levels | unknown | onset same period; build none; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | -0.69 sd/sd (identity) |
| 13 `msad.id.uw_profit:msad.dnl_npe` | MS&AD domestic non-life underwriting profit = MS&AD domestic non-life net premiums earned - MS&AD domestic non-life net incurred losses - MS&AD domestic non-life underwriting expenses: MS&AD domestic non-life net premiums earned is a total; weight derived at the construction levels | unknown | onset same period; build none; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | +0.71 sd/sd (identity) |
| 14 `msad-a-dnl-uw` | Underwriting profit before catastrophe-reserve movements is the insurance part of domestic non-life adjusted profit (adjusted profit adds the reserve movements back, so catastrophe losses hit it in full) | same scope and period; taxes sit in the residual | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | domestic non-life adjusted profit | +4.49 sd/sd (accounting) |
| 15 `s40` | Domestic non-life adjusted profit is one part of group adjusted profit (company definition); weight is its scale over the total's | same basis (group adjusted profit by business), period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | group adjusted profit | +0.50 sd/sd (accounting) |

Unresolved inputs: MS&AD auto rate revision schedule (disclosed not supplied); auto claim severity by company (not disclosed in reviewed sources); net premiums earned by line (disclosed not supplied); renewal retention by line (not disclosed in reviewed sources); reserve triangles by line (not disclosed in reviewed sources); settlement pattern by line (not disclosed in reviewed sources).

#### MS&AD capital and shareholder return

**Trigger:** overseas subsidiaries earn and can remit. **Endpoint:** MS&AD shareholder returns.

MS&AD international business profit → MS&AD dividends from overseas subsidiaries? → MS&AD deployable excess capital → MS&AD shareholder returns?  (? marks a step whose size is unknown)

Earnings capacity, parent cash, available capital and board payout policy are distinct; a profit move does not by itself decide a dividend.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `msad-c-intl-remit` | Overseas profit becomes parent cash only when subsidiaries remit dividends, subject to local capital rules (Lloyd's and local regulators) (overseas boards and regulators) | local capital surplus; no trapped cash; observable: dividends received from overseas subsidiaries | onset annual dividend cycle; build one year; persists per year; recognized parent accounts | inferred / inferred / unknown / unknown | trapped cash; local capital stress (e.g. after catastrophe years at Lloyd's) | dividends from overseas subsidiaries | unknown |
| 2 `msad-c-remit-capital` | Remitted cash adds to capital available at the parent (group capital management) | observable: parent liquidity | onset on receipt; build none; persists until used; recognized parent accounts | inferred / inferred / unknown / unknown | parent obligations | deployable excess capital | +0.20 sd/sd (stock-flow, accumulates per 365 days) |
| 3 `msad-c-capital-returns` | Capital beyond needs can fund buybacks under the board's capital policy; no automatic dividend conclusion follows (board) | ESR above the target range; parent cash available; no better use; observable: announced buybacks | onset next results or capital announcement; build over the year; persists per decision; recognized equity | inferred / inferred / unknown / unknown | acquisitions take priority; capital stress | shareholder returns | unknown |

Unresolved inputs: remittances by subsidiary (not disclosed in reviewed sources); shareholder return policy in force (disclosed not supplied).

#### MS&AD catastrophes, catastrophe reserves and reinsurance

**Trigger:** a heavy domestic typhoon or flood season. **Endpoint:** MS&AD net income.

Japan insured natural catastrophe losses → [company] MS&AD domestic natural catastrophe losses? → [reinsurance] MS&AD reinsurance cost? → [losses] MS&AD domestic non-life net incurred losses? → [reserve] MS&AD catastrophe loss reserve net provision? → [ceded] MS&AD domestic non-life net premiums earned? → [pass_through] MS&AD domestic fire rate revision? → MS&AD domestic fire premiums? → MS&AD domestic non-life net premiums written → MS&AD domestic non-life net premiums earned? → MS&AD domestic non-life underwriting profit → MS&AD domestic non-life underwriting profit → MS&AD domestic P&C profit → MS&AD group adjusted profit → MS&AD net income → MS&AD reserve add-back to net income? → MS&AD net income  (? marks a step whose size is unknown)

Catastrophe losses hit underwriting profit and group adjusted profit in full; the J-GAAP catastrophe-reserve reversal cushions net income only (adjusted profit adds reserve movements back). Reinsurance hardens at the next renewal and passes into fire rates.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [company] `msad-c-industrycat-losses` | Industry insured catastrophe losses fall on each insurer by its share of the exposed fire and auto book, net of its reinsurance (domestic claims) | MS&AD's share of exposed property in the affected region; reinsurance recoveries above the retention; observable: net incurred natural catastrophe losses versus the annual budget | onset event quarter; build 1-2 quarters of development; persists one-off per event; recognized incurred in the event quarter | inferred / inferred / unknown / inferred | reinsurance recoveries above the retention cap the net loss | MS&AD domestic catastrophe losses | unknown |
| 2 [reinsurance] `msad-c-industrycat-reins` | Heavy industry catastrophe years raise ceded reinsurance prices at the next renewal (reinsurers) | industry-wide losses and reinsurer capital constraints, not one company's losses alone; observable: renewal rate-on-line for Japanese catastrophe programmes | onset next reinsurance renewal (often April for Japan); build one renewal; persists until capital returns; recognized ceded premium over the cover period | inferred / inferred / unknown / unknown | abundant reinsurance capital; changed retention | reinsurance cost | unknown |
| 3 [losses] `msad-c-cat-uw` | Net catastrophe losses are part of net incurred losses, so they lower underwriting profit in full before catastrophe-reserve movements; the variance against the annual budget is what moves results versus plan (domestic claims) | losses below the retention are borne net; observable: net incurred natural catastrophe losses versus budget | onset event quarter; build 1-2 quarters; persists one-off per event; recognized incurred in the event quarter | inferred / inferred / unknown / inferred | reinsurance recoveries above the retention | net incurred losses | unknown |
| 4 [reserve] `msad-c-cat-reserve` | Heavy catastrophe losses push a line's loss ratio over its statutory threshold, and the catastrophe loss reserve is reversed (the net provision falls or turns negative), cushioning net income but not adjusted profit (domestic non-life (J-GAAP reserving rules)) | J-GAAP catastrophe loss reserves; the line's loss ratio exceeds its reversal threshold; the reserve balance is not exhausted; observable: provision or reversal of catastrophe loss reserves by line | onset same fiscal year; build none; persists one-off per year; recognized fiscal-year results | inferred / inferred / unknown / inferred | loss ratio below the threshold (no reversal); an exhausted reserve; IFRS (no such reserve) | catastrophe reserve net provision | unknown; acts only while MS&AD domestic natural catastrophe losses is above 80 |
| 5 [ceded] `msad-c-reins-uw` | Higher reinsurance prices raise ceded premium, lowering net premiums earned (and so underwriting profit) unless passed into rates (domestic reinsurance buyers) | programme size unchanged; observable: ceded premium; reinsurance programme terms | onset renewal date; build over the cover period; persists one year per renewal; recognized ceded premium earned over the cover | inferred / inferred / unknown / unknown | a higher retention instead of a higher cost | net premiums earned | unknown |
| 6 [pass_through] `msad-c-reins-firerate` | Reinsurance cost increases are a cost of capacity that pricing reviews pass into fire and property rates (domestic pricing) | pricing discretion and competitor behavior allow pass-through; observable: fire rate revisions | onset 1-2 years; build one renewal cycle; persists until the next review; recognized earned over the term | inferred / inferred / unknown / unknown | competitors hold prices | fire rate change | unknown |
| 7 `msad-c-firerate-npw` | Fire rate revisions and reunderwriting raise fire premium per policy (multi-year policies reprice only at renewal) (domestic non-life) | policies renew at the new rate; long-term policies renew slowly; observable: fire premium growth | onset at renewal; build several years (long-term policies); persists until repriced; recognized written at renewal, earned over the term | inferred / inferred / unknown / unknown | lost volume; shorter policy terms | fire premiums written | unknown |
| 8 `msad-a-npw-fire` | Fire and allied lines premiums are one line of domestic net premiums written | unknown | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | domestic premiums written | +0.40 sd/sd (accounting) |
| 9 `msad-c-npw-earned` | Written premium is earned over the policy term; profit arrives only if the premium covers expected claims and expenses (domestic non-life) | price adequacy: combined ratio below 100%; observable: combined ratio on a matching earned/incurred basis | onset 1-2 quarters; build over the policy term; persists while priced adequately; recognized earned pro rata | inferred / inferred / unknown / inferred | inadequate pricing; claims arriving faster than premiums are repriced | net premiums earned | unknown |
| 10 `msad.id.uw_profit:msad.dnl_incurred_losses` | MS&AD domestic non-life underwriting profit = MS&AD domestic non-life net premiums earned - MS&AD domestic non-life net incurred losses - MS&AD domestic non-life underwriting expenses: MS&AD domestic non-life net incurred losses is a deduction; weight derived at the construction levels | unknown | onset same period; build none; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | -0.69 sd/sd (identity) |
| 11 `msad.id.uw_profit:msad.dnl_npe` | MS&AD domestic non-life underwriting profit = MS&AD domestic non-life net premiums earned - MS&AD domestic non-life net incurred losses - MS&AD domestic non-life underwriting expenses: MS&AD domestic non-life net premiums earned is a total; weight derived at the construction levels | unknown | onset same period; build none; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | +0.71 sd/sd (identity) |
| 12 `msad-a-dnl-uw` | Underwriting profit before catastrophe-reserve movements is the insurance part of domestic non-life adjusted profit (adjusted profit adds the reserve movements back, so catastrophe losses hit it in full) | same scope and period; taxes sit in the residual | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | domestic non-life adjusted profit | +4.49 sd/sd (accounting) |
| 13 `s40` | Domestic non-life adjusted profit is one part of group adjusted profit (company definition); weight is its scale over the total's | same basis (group adjusted profit by business), period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | group adjusted profit | +0.50 sd/sd (accounting) |
| 14 `msad-a-ni-gap` | Net income is group adjusted profit less the items the definition adds back; every operating change reaches net income through adjusted profit, so nothing is counted twice | same period and yen; the items added back are J-GAAP reserve provisions and the definition's other adjustments | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | a change of the adjusted-profit definition (e.g. excluding sale gains) moves items between the two views | net income | +0.55 sd/sd (accounting) |
| 15 `msad-c-reserve-addback` | The after-tax net provision is what adjusted profit adds back to net income; a reversal lowers the add-back (group reporting) | the adjusted-profit definition adds back catastrophe-reserve movements; observable: the company's adjusted-profit reconciliation | onset same period; build none; persists identity; recognized fiscal-year results | inferred / inferred / unknown / inferred | a definition change | reserve add-back | unknown |
| 16 `msad-a-ni-addback` | The after-tax net provision for catastrophe and price-fluctuation reserves is a charge in net income that adjusted profit adds back; a reversal year turns it negative and lifts net income above adjusted profit | J-GAAP reserves exist (they do not under IFRS) | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | net income | -0.36 sd/sd (accounting) |

Unresolved inputs: MS&AD catastrophe budget (disclosed not supplied); catastrophe reserve balance (disclosed not supplied); net premiums earned by line (disclosed not supplied); regional share of exposed property (not disclosed in reviewed sources); reinsurance programme terms (not disclosed in reviewed sources); reversal thresholds by line (not disclosed in reviewed sources); the company's net income to adjusted profit reconciliation (disclosed not supplied).

#### MS&AD strategic-equity reduction

**Trigger:** management sells strategic equities under the reduction plan. **Endpoint:** MS&AD deployable excess capital.

MS&AD strategic equity sales → [income] MS&AD dividends from domestic equities? → [gains] MS&AD gains on sales of strategic equity holdings? → [book] MS&AD strategic equity holdings → [risk] MS&AD economic solvency ratio? → [cash] MS&AD deployable excess capital → MS&AD domestic non-life net interest and dividends → MS&AD domestic P&C profit → MS&AD domestic P&C profit → MS&AD group adjusted profit → [returns] MS&AD shareholder returns? → [redeploy] MS&AD acquisition spend?  (? marks a step whose size is unknown)

Sales give up recurring dividends (negative), realize one-off gains that count in adjusted profit under the definition read here, shrink the book, release risk capital, and add deployable capital.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [income] `msad-c-sale-dividends` | Selling strategic equities gives up their future dividends, a recurring income loss (domestic non-life (sale decision under the reduction plan)) | proceeds are not reinvested at an equal running yield; observable: dividends from domestic stocks | onset next dividend dates; build as sales proceed; persists permanent; recognized dividend income | inferred / inferred / unknown / inferred | proceeds reinvested at a higher yield | dividends from domestic equities | unknown |
| 2 [gains] `msad-c-sale-gains` | Sales realize the gain over acquisition cost; a one-off that counts in adjusted profit under the definition read here, never recurring income (domestic non-life) | holdings carry gains (low acquisition cost); observable: gains on sales of securities | onset on sale; build as sales proceed; persists one-off; recognized the period of sale | inferred / inferred / unknown / inferred | sales of holdings near cost; impairments | gains on sales of strategic equities | unknown |
| 3 [book] `msad-c-sale-book` | Sales reduce the strategic equity book under the reduction plan (domestic non-life) | observable: market value of strategic equities | onset on sale; build over the plan; persists permanent; recognized period end | inferred / inferred / unknown / inferred | counterparties resist sales | strategic equity holdings | -0.27 sd/sd (stock-flow, accumulates per 365 days) |
| 4 [risk] `msad-c-sale-esr` | Selling equities and holding the proceeds in lower-risk assets lowers required capital more than economic capital (group capital management) | proceeds held in lower-risk assets or returned; observable: ESR after sales | onset on sale; build over the plan; persists permanent; recognized solvency reporting | inferred / inferred / unknown / unknown | proceeds redeployed into riskier assets or acquisitions | economic solvency ratio | unknown |
| 5 [cash] `msad-c-sale-capital` | After-tax proceeds and released risk capital add to capital that can be returned or redeployed; capital, not earnings (group capital management) | tax on realized gains paid; solvency above target range; observable: capital policy disclosures | onset on sale; build over the plan; persists until deployed; recognized capital reporting | inferred / inferred / unknown / unknown | capital stress elsewhere absorbs it | deployable excess capital | +0.50 sd/sd (stock-flow, accumulates per 365 days) |
| 6 `msad-a-inv-domeq` | Dividends from domestic equities (mostly strategic holdings) are one asset class of net interest and dividends | unknown | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | domestic net interest and dividends | +0.75 sd/sd (accounting) |
| 7 `msad-a-dnl-inv` | Recurring net interest and dividends (after income credited to savings-type policies) is the investment part of domestic non-life adjusted profit | same scope and period; dividends from overseas subsidiaries in it are eliminated on consolidation (held in the group residual) | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | domestic non-life adjusted profit | +1.03 sd/sd (accounting) |
| 8 `msad-a-dnl-xgain` | Realized gains on strategic-equity sales count in domestic non-life adjusted profit under the definition read here; they are non-recurring and held apart from recurring investment income | the adjusted-profit definition in force includes sale gains (to verify); a definition that excludes them moves this part to the net-income bridge | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | a definition that excludes sale gains from adjusted profit | domestic non-life adjusted profit | +1.92 sd/sd (accounting) |
| 9 `s40` | Domestic non-life adjusted profit is one part of group adjusted profit (company definition); weight is its scale over the total's | same basis (group adjusted profit by business), period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | group adjusted profit | +0.50 sd/sd (accounting) |
| 10 [returns] `msad-c-capital-returns` | Capital beyond needs can fund buybacks under the board's capital policy; no automatic dividend conclusion follows (board) | ESR above the target range; parent cash available; no better use; observable: announced buybacks | onset next results or capital announcement; build over the year; persists per decision; recognized equity | inferred / inferred / unknown / unknown | acquisitions take priority; capital stress | shareholder returns | unknown |
| 11 [redeploy] `msad-c-capital-ma` | Excess capital funds acquisitions and strategic stakes when a target fits risk appetite and price discipline (group management (M&A)) | an opportunity at an acceptable price; observable: announced deals | onset deal announcement; build closing (months); persists per deal; recognized at closing | inferred / inferred / unknown / unknown | no fitting target; price too high | acquisition spend | unknown |

Unresolved inputs: MS&AD reduction plan and its end date (disclosed not supplied); acquisition cost of strategic holdings (disclosed not supplied); dividend yield of the holdings sold (not disclosed in reviewed sources); shareholder return policy in force (disclosed not supplied); whether the adjusted-profit definition in force includes gains on sales of strategic equities (disclosed not supplied).

#### MS&AD domestic yields to investment income and life

**Trigger:** super-long JGB yields rise. **Endpoint:** MS&AD group adjusted profit.

JGB 30Y yield → [assets] MS&AD domestic non-life new-money yield? → [liabilities] MS&AD investment income credited to savings-type policies? → [life] MSI Aioi Life adjusted profit? → MS&AD domestic bond book yield? → MS&AD income from domestic bonds → MS&AD domestic non-life net interest and dividends → MS&AD domestic non-life net interest and dividends → MS&AD domestic P&C profit → MS&AD group adjusted profit → MS&AD domestic life adjusted profit → MS&AD group adjusted profit  (? marks a step whose size is unknown)

A JGB move reaches only new money at that tenor; income credited to savings-type policies absorbs part; the life company is the long-duration book. s38 is the reduced-form summary of this path and is never added to it.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [assets] `msad-c-jgb30-nmy` | Super-long JGB yields set the yield only on new money invested at super-long tenors; they do not apply to the whole domestic book (domestic asset management) | some new money goes to super-long tenors (P&C liabilities are shorter than a life insurer's); observable: tenor mix of purchases | onset at purchase; build as cash reinvests; persists to maturity; recognized accrual | inferred / inferred / unknown / unknown | no super-long purchases; allocation to other assets | new-money yield | unknown |
| 2 [liabilities] `msad-c-jgb30-deposit` | New savings-type policies are priced at higher assumed rates when yields are higher, so more investment income is credited to policyholders (counter-path; the credit is negative) (domestic product pricing) | savings-type products are still sold; assumed rates follow yields; observable: investment income transferred to deposit premiums | onset new policies; build years; persists over policy terms; recognized accrual | inferred / inferred / unknown / unknown | a run-off savings book with fixed rates | income credited to savings-type policies | unknown |
| 3 [life] `msad-c-jgb30-life` | The protection life company invests long-duration liabilities in super-long JGBs; new money at higher yields widens the spread over assumed rates, slowly (life asset-liability management) | new money and maturities reinvest at super-long tenors; assumed rates fixed; observable: life investment yield; reinvested share | onset 1-2 quarters; build many years (low turnover); persists to maturity; recognized accrual | inferred / inferred / unknown / unknown | surrenders; policy-reserve-matching bonds already locked in | MSI Aioi Life adjusted profit | unknown |
| 4 `msad-c-nmy-bondinc` | A higher new-money yield lifts the book yield only as maturing cohorts are replaced, not across the whole bond portfolio (domestic asset management) | reinvestable cash exists (see the reinvestment path); new yield above that of maturing bonds; observable: domestic bond income yield; investment-income bridge | onset 1-2 quarters; build years (turnover); persists to maturity; recognized accrual | inferred / broker / unknown / unknown | low turnover; credit losses | domestic bond book yield | unknown |
| 5 `msad.id.bond_income:msad.dnl_bond_book_yield` | MS&AD income from domestic bonds = 0.01 x MS&AD domestic bond portfolio x MS&AD domestic bond book yield: MS&AD domestic bond book yield is a factor; weight derived at the construction levels | unknown | onset same period; build none; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | +1.00 sd/sd (identity) |
| 6 `msad-a-inv-dombond` | Interest on domestic bonds is one asset class of net interest and dividends, and the one JGB yields reach | unknown | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | domestic net interest and dividends | +0.25 sd/sd (accounting) |
| 7 `msad-a-inv-deposit` | Investment income credited to savings-type (maturity-refund) policies is the liability side of net interest and dividends (negative) | unknown | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | domestic net interest and dividends | +0.19 sd/sd (accounting) |
| 8 `msad-a-dnl-inv` | Recurring net interest and dividends (after income credited to savings-type policies) is the investment part of domestic non-life adjusted profit | same scope and period; dividends from overseas subsidiaries in it are eliminated on consolidation (held in the group residual) | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | domestic non-life adjusted profit | +1.03 sd/sd (accounting) |
| 9 `s40` | Domestic non-life adjusted profit is one part of group adjusted profit (company definition); weight is its scale over the total's | same basis (group adjusted profit by business), period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | group adjusted profit | +0.50 sd/sd (accounting) |
| 10 `msad-a-life-mail` | MSI Aioi Life is one of the two domestic life companies | unknown | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | domestic life adjusted profit | +0.47 sd/sd (accounting) |
| 11 `msad-a-gap-life` | Domestic life adjusted profit is one part of group adjusted profit (company definition) | same basis (group adjusted profit by business), period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | group adjusted profit | +0.73 sd/sd (accounting) |

Unresolved inputs: life reinvested share per year (not disclosed in reviewed sources); reinvested share of the domestic bond portfolio per year (not disclosed in reviewed sources); savings-type policy reserves and assumed rates (not disclosed in reviewed sources); tenor mix of domestic bond purchases (not disclosed in reviewed sources).

#### MS&AD equity marks on strategic holdings

**Trigger:** Japanese equities move. **Endpoint:** MS&AD economic solvency ratio.

Japan equity index (TOPIX) → MS&AD strategic equity holdings? → [equity] MS&AD shareholders' equity? → [solvency] MS&AD economic solvency ratio? → [valuation] MS&AD unrealized gains on strategic holdings per share? → MS&AD share price?  (? marks a step whose size is unknown)

A large strategic book moves net assets, the ESR and the holding value per share that a sum-of-the-parts adds to core earnings value.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `msad-c-topix-xholding` | Strategic equities are marked at market; a rising index raises their value; a sum-of-the-parts values the unrealized gain separately from core earnings (market) | holdings track the broad index (a concentrated book, e.g. auto-group names, may not); observable: market value of strategic equities; unrealized gains per share | onset immediate; build none; persists until sold; recognized period end | broker / inferred / unknown / inferred | sales shrink the book; concentration in a few names | strategic equity holdings | unknown |
| 2 [equity] `msad-c-xholding-equity` | Market moves on available-for-sale equities change net assets (after tax), never adjusted profit until sold (group accounts) | observable: valuation difference on available-for-sale securities | onset period end; build none; persists until reversal; recognized quarterly balance sheet | inferred / inferred / unknown / inferred | deferred tax absorbs part | shareholders' equity | unknown |
| 3 [solvency] `msad-c-xholding-esr` | A higher equity book raises economic capital (and equity risk, less than one for one) (economic solvency measurement) | observable: ESR equity sensitivity | onset immediate; build none; persists until sold; recognized solvency reporting | inferred / inferred / unknown / inferred | the equity risk charge rises with the book | economic solvency ratio | unknown |
| 4 [valuation] `msad-c-xholding-pershare` | Unrealized gains per share are the book above cost, after tax, over shares outstanding (valuation) | acquisition cost of the holdings is unchanged (sales lower both); observable: unrealized gains on strategic holdings per share | onset period end; build none; persists until sold; recognized period-end disclosure | broker / inferred / unknown / inferred | buybacks change the share count | unrealized gains per share | unknown |
| 5 `msad-c-pershare-price` | A sum-of-the-parts value adds the unrealized holding gains per share at a discount for the time to realization (a valuation choice) (investors and analysts) | the market values holdings separately from core earnings; observable: price target build-ups; price-to-book | onset as disclosed; build none; persists while held; recognized market price | broker / broker / unknown / unknown | a market that values only earnings | share price | unknown |

Unresolved inputs: ESR sensitivity to equity prices (disclosed not supplied); acquisition cost of strategic holdings (disclosed not supplied); strategic holdings by name and their index beta (disclosed not supplied); the market's discount on holding value (the broker's is one view) (found connected).

#### MS&AD FX hedge cost

**Trigger:** the US-Japan short-rate gap widens. **Endpoint:** MS&AD group adjusted profit.

Fed funds rate (midpoint) → MS&AD FX hedge cost on foreign bonds? → MS&AD income from foreign securities? → MS&AD domestic non-life net interest and dividends → MS&AD domestic P&C profit → MS&AD group adjusted profit  (? marks a step whose size is unknown)

Hedge cost consumes the yield on hedged foreign bonds; the BoJ side narrows it (msad-c-boj-hedge).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `msad-c-fed-hedge` | Hedging USD assets into yen costs roughly the US-Japan short-rate differential; a higher Fed rate widens it (FX forward market) | foreign bonds held FX-hedged with rolling short-dated forwards; observable: 3-month USD/JPY forward points | onset next roll; build within months; persists while the gap holds; recognized each roll | inferred / inferred / unknown / inferred | unhedged holdings; longer-dated hedges | FX hedge cost | unknown |
| 2 `msad-c-hedge-forinc` | Hedge cost consumes the yield benefit of hedged foreign bonds; net of hedging, a higher foreign yield may add little (domestic asset management) | a hedged foreign bond notional exists; the line where the hedge cost is booked is not stated in the reviewed sources; observable: hedge cost in results | onset next roll; build within a year; persists while hedged; recognized each roll | inferred / inferred / unknown / inferred | reducing the hedge ratio (adds FX risk) | foreign securities income | unknown |
| 3 `msad-a-inv-forsec` | Interest and dividends on foreign securities (after hedge costs where booked in income) are one asset class of net interest and dividends | unknown | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | domestic net interest and dividends | +0.56 sd/sd (accounting) |
| 4 `msad-a-dnl-inv` | Recurring net interest and dividends (after income credited to savings-type policies) is the investment part of domestic non-life adjusted profit | same scope and period; dividends from overseas subsidiaries in it are eliminated on consolidation (held in the group residual) | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | domestic non-life adjusted profit | +1.03 sd/sd (accounting) |
| 5 `s40` | Domestic non-life adjusted profit is one part of group adjusted profit (company definition); weight is its scale over the total's | same basis (group adjusted profit by business), period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | group adjusted profit | +0.50 sd/sd (accounting) |

Unresolved inputs: hedged notional and hedge ratio (not disclosed in reviewed sources); line where hedge cost is booked (not disclosed in reviewed sources).

#### MS&AD growth execution

**Trigger:** an acquisition or stake within risk appetite. **Endpoint:** MS&AD group adjusted profit.

MS&AD deployable excess capital → MS&AD acquisition spend? → [earnings] MS&AD acquired-business earnings? → [capital] MS&AD economic solvency ratio? → MS&AD international adjusted profit at constant FX? → MS&AD international business profit → MS&AD group adjusted profit  (? marks a step whose size is unknown)

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `msad-c-capital-ma` | Excess capital funds acquisitions and strategic stakes when a target fits risk appetite and price discipline (group management (M&A)) | an opportunity at an acceptable price; observable: announced deals | onset deal announcement; build closing (months); persists per deal; recognized at closing | inferred / inferred / unknown / unknown | no fitting target; price too high | acquisition spend | unknown |
| 2 [earnings] `msad-c-ma-earnings` | An acquisition or stake adds earnings after financing cost, reserve adequacy and integration; the price decides the return (group management) | price below value; reserves adequate; observable: acquired-business profit versus the deal case | onset closing; build 1-3 years; persists while owned; recognized from closing (consolidated or equity method) | inferred / inferred / unknown / unknown | overpaying; reserve deficiencies; integration failure | acquired-business earnings | unknown |
| 3 [capital] `msad-c-ma-esr` | Acquisitions consume economic capital (price above net assets plus the acquired risk) (group capital management) | observable: ESR after the deal | onset closing; build none; persists until earned back; recognized solvency reporting | inferred / inferred / unknown / unknown | funded by new equity or partner capital | economic solvency ratio | unknown |
| 4 `msad-c-acquired-intl` | Acquired overseas earnings join international profit at constant FX (inorganic growth, kept apart from organic) (group reporting) | consolidated, or equity-accounted (profit share only); observable: growth split organic versus inorganic | onset closing; build none; persists while owned; recognized from closing | inferred / inferred / unknown / unknown | a stake below significant influence (dividends only) | international profit at constant FX | unknown |
| 5 `msad-a-intl-translate` | Yen international profit is constant-FX profit times the change in reporting rates; this link carries the local operating change at constant rates, s35 carries the dollar rate (in log terms the two add) | translation at period-average rates; growth ex-FX reported separately; observable: reported growth versus growth at constant FX | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | a hedge of translated earnings would change the yen outcome (none represented); sterling and euro rates are not carried (only USD/JPY is) | international adjusted profit in yen | +1.00 sd/sd (accounting) |
| 6 `s39` | International adjusted profit is one part of group adjusted profit (company definition); weight is its scale over the total's | same basis (group adjusted profit by business), period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | group adjusted profit | +0.36 sd/sd (accounting) |

#### MS&AD international catastrophes and the rate cycle

**Trigger:** a heavy US hurricane or global catastrophe year. **Endpoint:** MS&AD group adjusted profit.

US insured natural catastrophe losses → [losses] MS&AD international catastrophe losses? → [hardening] MS&AD international renewal pricing? → MS&AD international underwriting profit? → [volume] MS&AD international net premiums written? → [margin] MS&AD international underwriting profit? → MS&AD international underwriting profit? → MS&AD international adjusted profit at constant FX → MS&AD international business profit → MS&AD group adjusted profit  (? marks a step whose size is unknown)

The same catastrophe year costs the reinsurance and Lloyd's books now and hardens rates for the next renewals; MS Amlin carries most of it.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [losses] `msad-c-uscat-intlcat` | Industry catastrophe losses in the US and elsewhere fall on the overseas property reinsurance and Lloyd's books by their share (overseas claims) | share of the market's property catastrophe capacity; retrocession above the retention; observable: international natural catastrophe losses versus budget | onset event quarter; build 1-2 quarters; persists one-off per event; recognized incurred in the event quarter | inferred / inferred / unknown / inferred | retrocession recoveries; reduced property catastrophe appetite | international catastrophe losses | unknown |
| 2 [hardening] `msad-c-uscat-intlrate` | Heavy catastrophe years raise property and reinsurance rates at the next renewals (the reinsurance and specialty market) | industry capital is depleted; no new capacity floods in; observable: renewal rate change on property and reinsurance | onset next renewal (January, June); build one renewal cycle; persists until capital returns; recognized earned over the term | inferred / inferred / unknown / unknown | abundant alternative capital | international renewal rate change | unknown |
| 3 `msad-c-intlcat-uw` | Net catastrophe losses lower international underwriting profit in the event period (overseas units) | observable: international catastrophe losses versus budget | onset event quarter; build 1-2 quarters; persists one-off per event; recognized incurred | inferred / inferred / unknown / inferred | retrocession; favorable development elsewhere | international underwriting profit | unknown |
| 4 [volume] `msad-c-intlrate-npw` | Rate increases raise written premium at constant exposure (overseas underwriters) | observable: premium growth at constant FX split into rate and exposure | onset at renewal; build one cycle; persists while held; recognized written at renewal | inferred / inferred / unknown / unknown | lost business | international premiums written | unknown |
| 5 [margin] `msad-c-intlrate-uw` | Rate increases ahead of loss trend widen the underwriting margin as they earn through (overseas underwriters) | rate change exceeds loss-cost trend; observable: rate change versus loss trend; combined ratio | onset 1-2 quarters after renewal; build about a year; persists until trend catches up; recognized earned pro rata | inferred / inferred / unknown / unknown | loss trend above rate change | international underwriting profit | unknown |
| 6 `msad-c-intlnpw-uw` | Overseas premium growth earns into underwriting profit if priced adequately (overseas units) | adequate pricing; growth not in lines with deteriorating loss trend; observable: growth at constant FX and combined ratio by business | onset 1-2 quarters; build over the term; persists while priced adequately; recognized earned pro rata | inferred / inferred / unknown / inferred | growth into underpriced risk | international underwriting profit | unknown |
| 7 `msad-a-intl-uw` | International underwriting profit is the insurance part of international adjusted profit before translation | same scope, constant FX | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | international profit at constant FX | +1.29 sd/sd (accounting) |
| 8 `msad-a-intl-translate` | Yen international profit is constant-FX profit times the change in reporting rates; this link carries the local operating change at constant rates, s35 carries the dollar rate (in log terms the two add) | translation at period-average rates; growth ex-FX reported separately; observable: reported growth versus growth at constant FX | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | a hedge of translated earnings would change the yen outcome (none represented); sterling and euro rates are not carried (only USD/JPY is) | international adjusted profit in yen | +1.00 sd/sd (accounting) |
| 9 `s39` | International adjusted profit is one part of group adjusted profit (company definition); weight is its scale over the total's | same basis (group adjusted profit by business), period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | group adjusted profit | +0.36 sd/sd (accounting) |

Unresolved inputs: international catastrophe budget (not disclosed in reviewed sources).

#### MS&AD overseas translation

**Trigger:** the yen weakens against the dollar. **Endpoint:** MS&AD group adjusted profit.

USD/JPY → [translation] MS&AD international business profit → [reserves] MS&AD domestic non-life net incurred losses? → MS&AD group adjusted profit → MS&AD domestic non-life underwriting profit → MS&AD domestic P&C profit → MS&AD group adjusted profit  (? marks a step whose size is unknown)

Translation raises yen overseas profit while foreign-currency claims reserves at home cost part of it back (size unknown: no MS&AD sensitivity in the reviewed sources).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [translation] `s35` | Overseas profit earned in local currency translates into more yen when the yen is weaker (period-average rates); the operating result at constant FX is carried separately by msad-a-intl-translate (group reporting) | no hedge of translated earnings; sterling, euro and Asian currencies matter as well as the dollar, and only USD/JPY is carried; observable: reported growth versus growth at constant FX; a per-yen sensitivity of overseas profit (not in the reviewed sources) | onset same quarter (average rate); build through the fiscal year; persists while the rate holds; recognized quarterly results | broker / broker / assumption / inferred | foreign-currency claims reserves at home move the other way (msad-c-fx-reserves); investor-currency return is not issuer translation | international adjusted profit in yen | +0.40 sd/sd |
| 2 [reserves] `msad-c-fx-reserves` | The domestic P&C companies hold claims reserves in foreign currency (marine, overseas covers of Japanese clients); a weaker yen raises their yen value at the period-end rate, offsetting part of the translation gain (domestic non-life (reserving)) | foreign-currency outstanding claims reserves exist and are not matched by foreign-currency assets in the same line; observable: foreign-currency reserve provision in the P&C companies' results | onset period end; build none; persists until the rate reverses; recognized quarterly results at the period-end rate | inferred / inferred / unknown / inferred | asset-side FX gains in the same company; a reversal of the rate reverses it | net incurred losses | unknown |
| 3 `s39` | International adjusted profit is one part of group adjusted profit (company definition); weight is its scale over the total's | same basis (group adjusted profit by business), period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | group adjusted profit | +0.36 sd/sd (accounting) |
| 4 `msad.id.uw_profit:msad.dnl_incurred_losses` | MS&AD domestic non-life underwriting profit = MS&AD domestic non-life net premiums earned - MS&AD domestic non-life net incurred losses - MS&AD domestic non-life underwriting expenses: MS&AD domestic non-life net incurred losses is a deduction; weight derived at the construction levels | unknown | onset same period; build none; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | -0.69 sd/sd (identity) |
| 5 `msad-a-dnl-uw` | Underwriting profit before catastrophe-reserve movements is the insurance part of domestic non-life adjusted profit (adjusted profit adds the reserve movements back, so catastrophe losses hit it in full) | same scope and period; taxes sit in the residual | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | domestic non-life adjusted profit | +4.49 sd/sd (accounting) |
| 6 `s40` | Domestic non-life adjusted profit is one part of group adjusted profit (company definition); weight is its scale over the total's | same basis (group adjusted profit by business), period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | group adjusted profit | +0.50 sd/sd (accounting) |

Unresolved inputs: MS&AD per-yen sensitivity of profit (not disclosed in reviewed sources).

#### MS&AD US and European yields to overseas income and annuity sales

**Trigger:** US Treasury yields rise. **Endpoint:** MS&AD group adjusted profit.

UST 10Y yield → [international] MS&AD international new-money yield? → [domestic_foreign] MS&AD income from foreign securities? → [primary_life] MSI Primary Life annuity sales? → MS&AD international investment income? → MS&AD international adjusted profit at constant FX → MS&AD international business profit → MS&AD group adjusted profit → MS&AD domestic non-life net interest and dividends → MS&AD domestic P&C profit → MS&AD group adjusted profit → MSI Primary Life adjusted profit? → MS&AD domestic life adjusted profit → MS&AD group adjusted profit  (? marks a step whose size is unknown)

US yields reach the reinvesting share of the overseas books, the domestic companies' foreign bonds (before hedge cost), and the bank-channel annuity business. Euro yields reach the same new-money yield through msad-c-bund-nmy (a parallel driver, not a step here). s36 and s37 are reduced-form summaries and are never added to this path.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [international] `msad-c-ust-nmy` | US Treasury yields plus spreads set the yield on new USD fixed income bought by the overseas units; they do not apply to all international assets (sterling, euro and Asian books differ) (overseas asset management) | purchases are fixed-rate USD bonds near that tenor; spreads unchanged; observable: new-money yield of the overseas units | onset at purchase; build as the book turns over; persists to maturity; recognized accrual | inferred / inferred / unknown / unknown | spread tightening; allocation to floating-rate assets | international new-money yield | unknown |
| 2 [domestic_foreign] `msad-c-ust-forinc` | The domestic companies' foreign bond purchases earn the higher US yield, before hedge cost (domestic asset management) | new money goes to foreign bonds; the hedge cost (msad-c-hedge-forinc) is the counter-path; observable: foreign securities income | onset at purchase; build years; persists to maturity; recognized accrual | inferred / inferred / unknown / unknown | hedge cost rising with the same rate move | foreign securities income | unknown |
| 3 [primary_life] `msad-c-ust-primary` | Higher US yields make foreign-currency fixed annuities sold through banks more attractive, lifting MSI Primary Life sales (bank-channel customers) | yen deposit and JGB alternatives stay less attractive; FX risk acceptable to buyers; observable: foreign-currency annuity sales | onset 1-2 quarters; build within a year; persists while the yield gap holds; recognized premium income at sale | inferred / inferred / unknown / unknown | higher yen yields (domestic alternatives) or a strong-yen scare | annuity sales | unknown |
| 4 `msad-c-intl-nmy-income` | Higher new-money yields raise income on the share of the overseas book that reinvests each year (overseas units) | turnover of the fixed-rate book; floating-rate assets reprice faster; observable: portfolio income yield of the overseas units | onset 1-2 quarters; build years; persists to maturity; recognized accrual | inferred / inferred / unknown / unknown | credit losses; lower turnover | international investment income | unknown |
| 5 `msad-a-intl-inv` | International investment income is the investment part of international adjusted profit before translation | same scope, constant FX | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | international profit at constant FX | +0.71 sd/sd (accounting) |
| 6 `msad-a-intl-translate` | Yen international profit is constant-FX profit times the change in reporting rates; this link carries the local operating change at constant rates, s35 carries the dollar rate (in log terms the two add) | translation at period-average rates; growth ex-FX reported separately; observable: reported growth versus growth at constant FX | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | a hedge of translated earnings would change the yen outcome (none represented); sterling and euro rates are not carried (only USD/JPY is) | international adjusted profit in yen | +1.00 sd/sd (accounting) |
| 7 `s39` | International adjusted profit is one part of group adjusted profit (company definition); weight is its scale over the total's | same basis (group adjusted profit by business), period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | group adjusted profit | +0.36 sd/sd (accounting) |
| 8 `msad-a-inv-forsec` | Interest and dividends on foreign securities (after hedge costs where booked in income) are one asset class of net interest and dividends | unknown | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | domestic net interest and dividends | +0.56 sd/sd (accounting) |
| 9 `msad-a-dnl-inv` | Recurring net interest and dividends (after income credited to savings-type policies) is the investment part of domestic non-life adjusted profit | same scope and period; dividends from overseas subsidiaries in it are eliminated on consolidation (held in the group residual) | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | domestic non-life adjusted profit | +1.03 sd/sd (accounting) |
| 10 `s40` | Domestic non-life adjusted profit is one part of group adjusted profit (company definition); weight is its scale over the total's | same basis (group adjusted profit by business), period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | group adjusted profit | +0.50 sd/sd (accounting) |
| 11 `msad-c-primary-sales-profit` | Annuity sales grow the in-force book, whose spread and fees earn over the policy term; under J-GAAP the year of sale can carry new-business strain (MSI Primary Life) | spreads over guaranteed rates hold; surrenders are moderate; observable: in-force reserves; adjusted profit of the company | onset 1-2 years; build over the policy term; persists while in force; recognized accrual | inferred / inferred / unknown / unknown | new-business strain in the year of sale; market value adjustments; surrenders | MSI Primary Life adjusted profit | unknown |
| 12 `msad-a-life-primary` | MSI Primary Life is the other domestic life company (bank-channel savings and foreign-currency annuities) | unknown | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | domestic life adjusted profit | +0.89 sd/sd (accounting) |
| 13 `msad-a-gap-life` | Domestic life adjusted profit is one part of group adjusted profit (company definition) | same basis (group adjusted profit by business), period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | group adjusted profit | +0.73 sd/sd (accounting) |

Unresolved inputs: currency mix of the overseas portfolios (not disclosed in reviewed sources); foreign-currency annuity sales (not disclosed in reviewed sources); reinvested share of the overseas portfolios per year (not disclosed in reviewed sources).

#### MS&AD policy growth

**Trigger:** customers' insurable exposures grow (vehicles, property, commercial activity). **Endpoint:** MS&AD group adjusted profit.

Japan real GDP growth → MS&AD domestic insured exposure? → MS&AD domestic non-life net premiums written? → [earned] MS&AD domestic non-life net premiums earned? → [expense_ratio] MS&AD domestic non-life expense ratio → MS&AD domestic non-life combined ratio → MS&AD domestic non-life underwriting profit → MS&AD domestic P&C profit → MS&AD group adjusted profit  (? marks a step whose size is unknown)

Exposure growth reaches profit only through earned premium at adequate prices; it also spreads fixed costs. The Toyota dealer channel feeds the same exposure (msad-c-toyota-exposure).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `msad-c-exposure` | Domestic activity grows what customers need insured (vehicles, property values, commercial activity, new risks) (customers (households and companies)) | insurable activity grows, not only nominal prices; observable: new vehicle registrations, construction starts, commercial activity indices | onset 1-2 quarters; build 1 year; persists while activity holds; recognized written at renewal | inferred / inferred / unknown / unknown | a shrinking vehicle fleet (a mature market limits premium growth); exposure growth without matching price | insured exposure | unknown |
| 2 `msad-c-exposure-npw` | More insured units at the same rate raise new business and renewal premiums, subject to underwriting appetite (domestic underwriters and agents) | underwriting appetite accepts the added risk at adequate prices; observable: premium growth decomposed into exposure, rate and retention | onset at renewal; build one renewal cycle (about a year); persists while held; recognized written when bound, earned over the term | inferred / inferred / unknown / inferred | risk selection that declines growth; competitor pricing | premiums written | unknown |
| 3 [earned] `msad-c-npw-earned` | Written premium is earned over the policy term; profit arrives only if the premium covers expected claims and expenses (domestic non-life) | price adequacy: combined ratio below 100%; observable: combined ratio on a matching earned/incurred basis | onset 1-2 quarters; build over the policy term; persists while priced adequately; recognized earned pro rata | inferred / inferred / unknown / inferred | inadequate pricing; claims arriving faster than premiums are repriced | net premiums earned | unknown |
| 4 [expense_ratio] `msad.id.expense_ratio:msad.dnl_npw` | MS&AD domestic non-life expense ratio = 100 x MS&AD domestic non-life underwriting expenses / MS&AD domestic non-life net premiums written: MS&AD domestic non-life net premiums written is a denominator; weight derived at the construction levels | unknown | onset same period; build none; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | -0.81 sd/sd (identity) |
| 5 `msad-a-cr-expense` | The expense ratio (W/P) is the other term of the combined ratio | the Japanese convention adds an earned-basis loss ratio to a written-basis expense ratio | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | combined ratio | +0.45 sd/sd (accounting) |
| 6 `msad.id.uw_profit:msad.dnl_npe` | MS&AD domestic non-life underwriting profit = MS&AD domestic non-life net premiums earned - MS&AD domestic non-life net incurred losses - MS&AD domestic non-life underwriting expenses: MS&AD domestic non-life net premiums earned is a total; weight derived at the construction levels | unknown | onset same period; build none; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | +0.71 sd/sd (identity) |
| 7 `msad-a-dnl-uw` | Underwriting profit before catastrophe-reserve movements is the insurance part of domestic non-life adjusted profit (adjusted profit adds the reserve movements back, so catastrophe losses hit it in full) | same scope and period; taxes sit in the residual | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | domestic non-life adjusted profit | +4.49 sd/sd (accounting) |
| 8 `s40` | Domestic non-life adjusted profit is one part of group adjusted profit (company definition); weight is its scale over the total's | same basis (group adjusted profit by business), period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | group adjusted profit | +0.50 sd/sd (accounting) |

Unresolved inputs: insured exposure by line (not disclosed in reviewed sources); net premiums earned by line (disclosed not supplied).

#### MS&AD reinvestment of the domestic bond portfolio

**Trigger:** domestic bonds mature or pay while market yields differ from book yields. **Endpoint:** MS&AD group adjusted profit.

MS&AD domestic bond portfolio → MS&AD domestic bond redemptions? → MS&AD domestic non-life cash available to reinvest? → MS&AD domestic non-life new investments? → MS&AD domestic bond portfolio → MS&AD income from domestic bonds → MS&AD domestic non-life net interest and dividends → MS&AD domestic P&C profit → MS&AD group adjusted profit → [payout] MS&AD shareholder returns? → [capital] MS&AD deployable excess capital  (? marks a step whose size is unknown)

The reinvestment transitions: existing bonds -> redemptions -> eligible cash -> chosen investments -> the bond book (a stock, msad.sf.domestic_bonds) -> earned income (book x book yield, msad.id.bond_income) -> net investment result -> segment profit -> group earnings and capacity. Sizes are unknown: no maturity ladder, allocation or turnover is in the reviewed sources, so a new yield is never applied to the whole portfolio.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `msad-c-portfolio-cash` | Bonds in the portfolio mature or are redeemed according to the maturity ladder (domestic asset management) | holdings actually mature or pay in the period; claims and liquidity needs are covered first; observable: maturity ladder and forecast net cash flows (not disclosed) | onset actual cash dates; build unknown; persists unknown; recognized not in profit until invested and earned | inferred / inferred / unknown / unknown | lower turnover; cash needed for claims or buybacks | domestic bond redemptions | unknown |
| 2 `msad-c-redeem-cash` | Redemptions, with coupons and net premium cash after claims and liquidity needs, are the cash that can reinvest (domestic asset management) | claims and liquidity needs are covered first; observable: forecast net cash flows (not disclosed) | onset actual cash dates; build none; persists per period; recognized not in profit until invested and earned | inferred / inferred / unknown / unknown | cash needed for claims or buybacks reduces the deployable balance | cash available to reinvest | unknown |
| 3 `msad-c-cash-invest` | The mandate, risk and capital budget, and asset allocation decide which assets, currencies and tenors the cash buys (investment committee) | allocation goes to fixed income at current yields rather than to cash or returns; observable: trades, currency and tenor choices (not disclosed) | onset execution dates; build unknown; persists holding period; recognized none until income accrues | inferred / inferred / unknown / unknown | allocation to other assets changes the yield exposure | new investments | unknown |
| 4 `msad-c-invest-income` | New purchases add to the domestic bond book, which earns at the book yield (msad.id.bond_income): incremental income = cash invested x incremental yield, by cohort (domestic asset management) | the actual yield exceeds that of the maturing assets; credit performance holds; observable: income yield and the investment-income bridge | onset from purchase date; build accrues cohort by cohort; persists to maturity; recognized accrual each quarter | inferred / inferred / unknown / inferred | defaults, a lower actual yield or delayed investment | domestic bond portfolio | +1.67 sd/sd (stock-flow, accumulates per 365 days) |
| 5 `msad.id.bond_income:msad.dnl_domestic_bonds` | MS&AD income from domestic bonds = 0.01 x MS&AD domestic bond portfolio x MS&AD domestic bond book yield: MS&AD domestic bond portfolio is a factor; weight derived at the construction levels | unknown | onset same period; build none; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | +0.30 sd/sd (identity) |
| 6 `msad-a-inv-dombond` | Interest on domestic bonds is one asset class of net interest and dividends, and the one JGB yields reach | unknown | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | domestic net interest and dividends | +0.25 sd/sd (accounting) |
| 7 `msad-a-dnl-inv` | Recurring net interest and dividends (after income credited to savings-type policies) is the investment part of domestic non-life adjusted profit | same scope and period; dividends from overseas subsidiaries in it are eliminated on consolidation (held in the group residual) | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | domestic non-life adjusted profit | +1.03 sd/sd (accounting) |
| 8 `s40` | Domestic non-life adjusted profit is one part of group adjusted profit (company definition); weight is its scale over the total's | same basis (group adjusted profit by business), period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | group adjusted profit | +0.50 sd/sd (accounting) |
| 9 [payout] `msad-c-gap-returns` | Dividends and buybacks follow a payout policy on group adjusted profit; higher recurring profit supports a higher payout, by board decision (board) | ESR within or above target; payout policy unchanged; observable: dividend per share, buybacks and total payout ratio announcements | onset next fiscal-year decision; build annual; persists progressive dividend policy; recognized on declaration | inferred / inferred / unknown / unknown | capital stress; a payout ratio on a definition that excludes sale gains | shareholder returns | unknown |
| 10 [capital] `msad-c-gap-capital` | Adjusted profit retained after payout adds to capital (earnings capacity, distinct from parent cash and regulatory capital) (group) | observable: ESR roll-forward | onset period end; build none; persists cumulative; recognized capital reporting | inferred / inferred / unknown / unknown | payout above earnings | deployable excess capital | +0.15 sd/sd (stock-flow, accumulates per 365 days) |

Unresolved inputs: allocation by asset class, currency and tenor (not disclosed in reviewed sources); cohort sizes (not disclosed in reviewed sources); maturity ladder of the domestic bond portfolio (not disclosed in reviewed sources); net premium cash flow (not disclosed in reviewed sources); shareholder return policy in force (disclosed not supplied); yield of maturing bonds (not disclosed in reviewed sources).

#### MS&AD US casualty reserves and specialty repricing

**Trigger:** US liability claim costs (legal and social inflation) rise. **Endpoint:** MS&AD group adjusted profit.

US liability claim severity → [reserves] MS&AD international prior-year reserve development? → [repricing] MS&AD international renewal pricing? → MS&AD international underwriting profit? → MS&AD international underwriting profit? → MS&AD international adjusted profit at constant FX → MS&AD international business profit → MS&AD group adjusted profit  (? marks a step whose size is unknown)

The same severity trend reaches the overseas casualty books as reserve charges and the specialty market as repricing.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [reserves] `msad-c-usliab-pyd` | Rising US liability claim costs (legal and social inflation) raise prior-year development on the overseas casualty and specialty books (Lloyd's and US) (overseas reserving) | long-tail US casualty exposure in the overseas books; older accident years still open; observable: prior-year development by business | onset next reserve review; build several years; persists one-off per review; recognized quarterly results | inferred / inferred / unknown / unknown | reserve margins; reinsurance on prior years; a smaller US casualty book than the peer's | international prior-year development | unknown |
| 2 [repricing] `msad-c-usliab-rate` | Specialty underwriters raise US liability rates (D&O and other financial lines) to cover the higher severity trend; the overseas specialty units write US D&O (specialty underwriters and the market) | market-wide repricing; capacity exits; observable: renewal rate change on US D&O and casualty | onset 1-2 quarters; build one renewal cycle; persists while severity persists; recognized earned over the term | broker / inferred / unknown / unknown | soft market; new capacity; the overseas units' D&O share is not known | international renewal rate change | unknown |
| 3 `msad-c-pyd-uw` | Adverse prior-year development is a charge to international underwriting profit in the period booked (overseas units) | observable: prior-year development disclosed by business | onset booking quarter; build none; persists one-off; recognized quarterly results | inferred / inferred / unknown / inferred | favorable development in other lines | international underwriting profit | unknown |
| 4 `msad-c-intlrate-uw` | Rate increases ahead of loss trend widen the underwriting margin as they earn through (overseas underwriters) | rate change exceeds loss-cost trend; observable: rate change versus loss trend; combined ratio | onset 1-2 quarters after renewal; build about a year; persists until trend catches up; recognized earned pro rata | inferred / inferred / unknown / unknown | loss trend above rate change | international underwriting profit | unknown |
| 5 `msad-a-intl-uw` | International underwriting profit is the insurance part of international adjusted profit before translation | same scope, constant FX | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | international profit at constant FX | +1.29 sd/sd (accounting) |
| 6 `msad-a-intl-translate` | Yen international profit is constant-FX profit times the change in reporting rates; this link carries the local operating change at constant rates, s35 carries the dollar rate (in log terms the two add) | translation at period-average rates; growth ex-FX reported separately; observable: reported growth versus growth at constant FX | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | a hedge of translated earnings would change the yen outcome (none represented); sterling and euro rates are not carried (only USD/JPY is) | international adjusted profit in yen | +1.00 sd/sd (accounting) |
| 7 `s39` | International adjusted profit is one part of group adjusted profit (company definition); weight is its scale over the total's | same basis (group adjusted profit by business), period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | public_not_supplied / public_not_supplied / inferred / public_not_supplied | unknown | group adjusted profit | +0.36 sd/sd (accounting) |

Unresolved inputs: MS&AD US D&O premium share (not disclosed in reviewed sources); US casualty exposure of the overseas books (not disclosed in reviewed sources).

## Validation

`tests/scenario/test_construction_msad.py` (loads sally_demo once):

- Structure: no `validate_construction` problems for the company; the twelve compositions and fifteen paths exist;
  every path step has a transition and every uncalibrated step a sign and an "unknown" magnitude; the first responses to
  a shared driver are parallel branches from one value; the reinvestment path's first six steps are the six transitions
  in order, starting at the domestic bond portfolio, with payout and capital as branches; s36–s38 are never steps of the
  paths they summarize.
- Financial integrity: every part of an additive view has a fixed-weight accounting link to its total, with its native
  sd over the total's as the weight; one unit per view; a residual in every view but the combined-ratio identity; the
  synthetic priors reconcile within 0.5% at the construction levels, counting each part with its link's sign (the reserve
  add-back subtracts); net income is downstream of adjusted profit; the catastrophe-reserve reversal reaches net income
  and never adjusted profit; sale gains are a separate part, never recurring income; strategic-equity sales reach profit
  only as realized gains and forgone dividends; bond, liability and equity marks never reach adjusted profit; capital is
  a non-additive stock with flows; no maturity ladder value exists.
- Calibration and inputs: no behavioural link carries a new size (only identity and stock-flow terms do, with derived
  weights); s35–s38 keep their sizes with an "assumption" magnitude and a scope statement; every input says whether
  the material was searched (no `not_yet_reviewed`); shared drivers are reused, never redefined.
- Conversion (Oct 18): one driving view per total (domestic profit: by source drives, by company reconciles, as
  `msad.mx.domestic_nonlife`); the five identities and three stock-flows exist and reconcile at the construction
  levels (`reconcile_identities`, `reconcile`, `reconcile_matrices`); the catastrophe-reserve reversal is a threshold
  state; every remaining tag says why it stays uncalibrated.
- Generalization: an oil-price shock, for which no path was written, traced through every link (below).
- Delivery: compositions in `financial_bridge`, named paths as `business_construction` transmission paths, s39/s40 as
  `accounting_identity` with metric `group_adjusted_profit`, uncalibrated links as `represented_uncalibrated` with their
  sign (all from `/v1/world-models/sally_demo/exports/v4.1.4`); new node ids returned by `/v1/world-models/sally_demo/graph`, the construction and
  trace endpoints.

Sally's expected paths (`tests/scenario/test_sally_expected_paths.py`) still pass: `international_profit`,
`domestic_profit` and `operating_profit` keep their ids, s35–s38 keep their sizes, and s39/s40 still carry a positive
effect into `operating_profit` (now fixed accounting weights 0.36 and 0.50).

**Generalization trace (oil shock).** `trace(oil.brent, msad)` after the conversion: 85 routes; 17 reach an endpoint
fully sized and 49 through at least one uncalibrated step. Fully sized: m02 → m08 → m16 → s35 (Japanese inflation, a
BoJ hike, a stronger yen, lower translated overseas profit); the Fed and UST routes into s36; m02 → m08 → m13 → m14 →
s38 (super-long JGBs into domestic non-life, the reduced form). Signed, then exact: claims severity raises incurred
losses (uncalibrated), and from there the loss ratio and underwriting profit follow by identity; new-money yields lift
the book yield (uncalibrated), and bond income follows by identity. Signed but unsized: a cheaper FX hedge into
foreign-securities income; savings-policy credits and the life spread; bond, liability and equity marks into the ESR
and the strategic book. Identity targets and stocks are endpoints, so routes stop there unless traced through totals.
Where it stops otherwise: the share price, which leads nowhere further; past the trace depth, inside the valuation
chain; and at every uncalibrated step, which a forecast lists as unquantified rather than adding zero.

## Completion report

Outcomes: built and verified (**BV**), built but uncalibrated (**BU**), blocked by a named input (**BL**), not built
(**NB**). Counts: 25 gaps; by category (first listed) MC 18, MAP 3, CAL 1, EXP 2, RET 1 (13 of them also CAL); by
outcome BV 7, BV with a blocked or uncalibrated part 4, BU 12, BL 1, NB 1.

| # | Outcome | What is in the model now | What remains |
|---|---|---|---|
| G01 | BV | `operating_profit` names its basis and exports as `group_adjusted_profit`; s39/s40 accounting with sd-ratio weights; life, financial services and an explicit residual added | levels synthetic: no MS&AD actuals in the material |
| G02 | BV (structure) / BL | `msad.comp.net_income_bridge`, one way, reserve add-back subtracting | the company's reconciliation table |
| G03 | BV | `msad.comp.domestic_nonlife_by_company`; alias moved to `msad.msi_profit` | profit by company |
| G04 | BV (structure) / BL | `msad.comp.domestic_nonlife_by_source`, sale gains a separate part | whether the plan in force counts sale gains |
| G05 | BV | `msad.comp.dnl_premiums_by_line`, `msad.comp.combined_ratio` | premiums and ratios by line; the company × line matrix |
| G06 | BU | `msad.path.auto_repricing` with retention and expense counter-steps | severity, rate schedule, retention, earned premium by line |
| G07 | BU | `msad.path.catastrophe_reserves`, reversal as a state-tagged counter-path into net income only | catastrophe budget, reserve balance and thresholds, reinsurance terms |
| G08 | BV | `msad.comp.international_by_business`, `msad.comp.international_by_source`, accounting translation | profit by business; non-dollar rates |
| G09 | BU | `msad.path.international_underwriting`, `msad.path.us_casualty_reserves` | catastrophe budget, US casualty exposure, D&O share |
| G10 | BV (structure) / BU | `msad.comp.domestic_life`; JGB and US-yield branches | life profit by company; annuity sales |
| G11 | BU | income and assets by class; `msad.path.reinvestment` with the six transitions | ladder, cash flow, allocation, turnover, maturing yields |
| G12 | BU | s36–s38 keep ids and sizes, with scope, "assumption" magnitude and a never-add rule | recalibrate once the structural paths can be sized |
| G13 | BU | `msad.path.fx_hedge_cost` (Fed up, BoJ down) | hedged notional and ratio; booking line |
| G14 | BU | `msad.path.asset_marks_liabilities` to net assets and ESR only | classification and duration; ESR sensitivities |
| G15 | BV (structure) / BU | `msad.path.cross_holding_disposal` | dividend yield sold, acquisition cost, the reduction plan |
| G16 | BU | `msad.path.equity_marks`, with the per-share holding value and its broker discount (cited) | holdings by name; ESR equity sensitivity |
| G17 | BU | `msad.path.overseas_translation`; counter-effect uncalibrated | a per-yen sensitivity |
| G18 | BU | capital values, `msad.path.capital_payout`, non-additive `msad.comp.capital_sources_uses` | remittances, the payout policy in force |
| G19 | BU | `msad.path.growth_execution` | deal terms |
| G20 | BU | `msad.path.policy_growth`; Toyota dealer-channel link | exposure by line; dealer-channel share |
| G21 | BL | one baseline bound (holding gains per share, end-FY3/26); one estimate kept apart | an MS&AD company model or results release |
| G22 | BV | objects present in the v4.1.4 export | — |
| G23 | BV | node ids served by the query, construction and trace endpoints | — |
| G24 | BV | shared insurer path untouched; company paths beside it | — |
| G25 | NB | the two market states reused from the `tokio_marine` entity, not duplicated | moving them to a market entity (a shared-file change) |

**Links, before → after the conversion.** 122 → 133 links touch MS&AD's values.

| | Before | After |
|---|---|---|
| accounting, quantified (fixed weights) | 42 | 39 |
| accounting, reconciling (no size: the company columns of the matrix) | 0 | 3 |
| identity terms (derived weights) | 0 | 11 |
| stock-flow terms (derived weights, accumulating) | 0 | 8 |
| calibrated causal (s35–s38, s71, the share-price default) | 6 | 6 |
| uncalibrated causal (sign only), of which state-dependent | 74, 0 | 66, 1 |

Converted: identities `msad.id.loss_ratio`, `msad.id.expense_ratio`, `msad.id.uw_profit` (replacing the combined-ratio
→ profit, written → expense-ratio and rate → loss-ratio links, which the identities now carry exactly),
`msad.id.bond_income`, `msad.id.adjusted_eps` (was `msad-c-gap-eps`); stock-flows `msad.sf.domestic_bonds` (was
`msad-c-invest-income`), `msad.sf.cross_holding_book` (was `msad-c-sale-book`), `msad.sf.excess_capital` (was
`msad-c-gap-capital`, `msad-c-sale-capital`, `msad-c-remit-capital`); state: `msad-c-cat-reserve` (threshold). Drivers that
acted on the ratios or on underwriting profit now act on their terms (severity, catastrophes and foreign-currency
reserves on incurred losses; reinsurance cost on earned premium; wages on expenses; new-money yield on the book yield).
Left uncalibrated, each with its reason in the note: premiums = exposure × price (the total of the driving line view),
auto premiums = policies × average premium (no such values), written → earned premium (no unearned-premium stock),
the reserve add-back = provision × (1 − tax) (a product needs two factors), the book yield as a cohort average,
holding gains per share (needs acquisition cost), the reinsurance-retention kink (an asymmetry needs a size), and
overseas underwriting profit (its terms are not represented). Inputs now distinguish 12 `disclosed_not_supplied`
(MS&AD discloses them publicly; not in the material) from 31 `not_disclosed_in_reviewed_sources`; company-structure
claims carry the support `public_not_supplied`.

**Reconciliation.** At the construction levels (medians) all 11 additive compositions and all 5 identities reconcile
within 0.5%; the matrix reconciles both views to the total (its cells are not given). At the posterior means the
lognormal parts exceed 0.5% in a few views, as before. At the local baselines every composition and identity is
`blocked` (no MS&AD level for any of its values), not flagged; the stock-flows cannot be rolled forward (no dated
stock levels).

**Inputs by status.** 44 distinct inputs: 1 `found_connected` (the broker's discount on holding value, cited), 12
`disclosed_not_supplied`, 31 `not_disclosed_in_reviewed_sources`, 0 `not_yet_reviewed`.

**Calculation coverage per path, now.** Own steps sized (accounting, identity and stock-flow, of which derived) versus
steps excluded (uncalibrated, with sign); the summary links s35–s38 are the only calibrated causal sizes.

| Path | Steps | Sized (of which derived) | Calibrated causal | Excluded (uncalibrated) | Inputs that block a size |
|---|---|---|---|---|---|
| `msad.path.policy_growth` | 8 | 5 (2) | 0 | 3 | exposure by line; earned premium by line |
| `msad.path.auto_repricing` | 15 | 8 (4) | 0 | 7 | severity by company; triangles; settlement; rate schedule (disclosed, not supplied); retention |
| `msad.path.catastrophe_reserves` | 16 | 7 (2) | 0 | 9 | catastrophe budget and reserve balance (disclosed, not supplied); regional share; reinsurance terms; thresholds |
| `msad.path.international_underwriting` | 9 | 3 (0) | 0 | 6 | international catastrophe budget |
| `msad.path.us_casualty_reserves` | 7 | 3 (0) | 0 | 4 | US casualty exposure; D&O share |
| `msad.path.domestic_yields` | 11 | 7 (1) | 0 | 4 | tenor mix; savings-policy reserves; reinvested shares |
| `msad.path.reinvestment` | 10 | 6 (3) | 0 | 4 | maturity ladder; net premium cash; allocation; payout policy |
| `msad.path.fx_hedge_cost` | 5 | 3 (0) | 0 | 2 | hedged notional and ratio; booking line |
| `msad.path.overseas_yields` | 13 | 8 (0) | 0 | 5 | currency mix; annuity sales; reinvested share |
| `msad.path.asset_marks_liabilities` | 5 | 0 | 0 | 5 | classification and duration; ESR rate sensitivity (disclosed, not supplied) |
| `msad.path.equity_marks` | 5 | 0 | 0 | 5 | holdings by name and acquisition cost (disclosed, not supplied) |
| `msad.path.cross_holding_disposal` | 11 | 6 (2) | 0 | 5 | dividend yield sold; reduction plan (disclosed, not supplied) |
| `msad.path.overseas_translation` | 6 | 4 (1) | 1 (s35) | 1 | per-yen sensitivity |
| `msad.path.capital_payout` | 3 | 1 (1) | 0 | 2 | remittances; payout policy (disclosed, not supplied) |
| `msad.path.growth_execution` | 6 | 2 (0) | 0 | 4 | none named (deal terms are event-specific) |

Every path's size still stops at its first uncalibrated (behavioural) step, but what follows a step into a term is now
exact: once incurred losses, earned premium, the bond book or its book yield move, the loss ratio, expense ratio,
underwriting profit, bond income, adjusted EPS and the capital stock follow with derived weights. Only overseas
translation is sized end to end (s35, then the accounting weights). The reduced forms s36–s38 still give the yield
routes a size and are never added to the structural paths.

**What a downstream agent can now trace or calculate.** Group adjusted profit as the sum of its businesses on one
basis, and net income downstream of it through the reserve add-back; domestic non-life by company and by source, with
sale gains apart from recurring income; premiums by line and the combined ratio; income and assets by class; the yen
international value as constant-FX profit times the rate; and, as signed mechanisms with conditions, timing, evidence
and breakers, how claims inflation, auto repricing, catastrophes and their reserves, reinsurance, international
catastrophes and US casualty, JGB and US yields, reinvestment, hedging, marks, strategic-equity sales, translation,
remittances, payout and acquisitions reach the right account.

**What remains unsupported.** Every size beyond the five existing records (no MS&AD sensitivity, ladder, notional,
triangle, budget or ESR shock is in the supplied material); every level (synthetic); the definition of adjusted profit
in force; non-dollar translation.

**What the method could not express for this company.**

1. *A definition that may move a part between views.* Whether sale gains count in adjusted profit decides whether
   `msad.dnl_xholding_gains` belongs to the business view or the net-income bridge. A composition member is fixed; there
   is no way to hold "member under definition A, bridge item under definition B" and switch on a dated definition.
2. *An identity held in both directions.* Net income and adjusted profit are two additive views of related totals. In a
   propagating graph only one can be driven; the other must be strictly downstream, or a change is counted twice. The
   bridge is therefore one-way, and net income cannot be observed and pushed back into adjusted profit.
3. *Structure from public knowledge.* The evidence scale has no level for "the company's own disclosure, known but not in
   the supplied material". Marking it `documented` would demand a citation that cannot exist; marking it `inferred`
   understates it. Most of this build sits on that gap.
4. *Shared market states owned by a company.* Japan claim severity and US liability severity live on the `tokio_marine`
   entity. Reusing them avoids a second id but routes MS&AD's paths through the peer's node; a market-state entity (or
   a shared-state scope) is missing.
5. *A basket translation.* International profit is earned in dollars, sterling, euros and Asian currencies; one rate
   link (s35) and one constant-FX value cannot split the effect by currency.
6. *A company × line matrix.* Premiums, loss ratios and auto exposure differ by company (the Toyota-affiliated insurer is
   auto heavy); the by-company and by-line views are separate, with no cross-classified cells.
7. *Ownership shares.* Equity-method stakes (Asian life, Australia) contribute a profit share, not consolidated profit;
   and the Toyota relationship runs both ways (dealer channel, and each holding the other's shares). Neither an
   ownership weight nor a link between two companies' balance sheets can be stated.
8. *Constants inside identities.* Underwriting profit is held as earned premium − losses − expenses because
   "earned premium × (1 − combined ratio)" needs a constant term, and the add-back = provision × (1 − tax) needs a
   one-factor product with a coefficient; neither form exists, so the add-back stays uncalibrated.
9. *Written to earned premium.* Earned = written − change in the unearned-premium reserve: a stock-flow whose stock is
   not represented, so the step from premiums written to premiums earned stays sign-only and every premium-driven size
   stops there.
10. *A matrix without cells.* Company × source is declared, but no cell is in the reviewed sources, so the matrix
    reconciles only the two views' totals; a driver specific to one company (the Toyota channel at Aioi Nissay Dowa)
    cannot be placed in a cell.
11. *Value names are extraction vocabulary.* A construction value's last word becomes a gazetteer head slot for the
    whole world: a value named "... securities held" made "held" a slot and stopped "The ECB held rates at ..." from
    resolving to the ECB's policy rate (caught by the ingest tests; renamed "holdings"). Nothing in the construction
    check warns that a new name can shadow another entity's surfaces.
