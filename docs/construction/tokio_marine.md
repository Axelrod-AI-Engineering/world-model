# Tokio Marine: business construction

<!-- toc -->
**Contents**

- [Plan round and the pack](#plan-round-and-the-pack)
  - [Part 1: before and after audit by canonical id](#part-1-before-and-after-audit-by-canonical-id)
  - [Part 2: composition and paths](#part-2-composition-and-paths)
  - [Part 3: evidence and calibration](#part-3-evidence-and-calibration)
  - [Part 4: end-to-end checks](#part-4-end-to-end-checks)
  - [Pack checklist](#pack-checklist)
- [Gap register](#gap-register)
- [Audit before modifying](#audit-before-modifying)
- [Definitions and bases](#definitions-and-bases)
- [Second review round](#second-review-round)
  - [Inputs by status](#inputs-by-status)
  - [Reconciliation](#reconciliation)
  - [Calculation coverage](#calculation-coverage)
- [Readable view](#readable-view)
  - [Business composition](#business-composition)
  - [Operating and financial paths](#operating-and-financial-paths)
- [Validation](#validation)
- [Completion report](#completion-report)
  - [Second round (Oct 18)](#second-round-oct-18)
  - [Conversion round (Oct 18)](#conversion-round-oct-18)
<!-- /toc -->

The construction lives in `data/worlds/sally_demo/construction/tokio_marine.yaml` (values, links with their
transitions, named paths, compositions) plus light edits to the `tokio_marine` entity and to m19–m23, s41, s55, s70.
This page is structure only: object ids, bases, categories, tests. The client-derived side (workbook rows, broker
figures, page and cell bindings, dated baselines) stays local under `data/sally_data/construction/tokio_marine/`
(`gap_evidence.md`, `sources.json`, `baselines.json`, `estimates.json`, and the full readable view with levels).

Source ids used in transitions (bindings are local): `tm.wb` sell-side company model workbook (J-GAAP history:
segments, line-of-business and investment-income detail); `tm.seg` client segment forecast model (IFRS adjusted net
income by business, driver layer, and the company disclosures it cites); `tm.co` company disclosures as cited in
`tm.seg` (not read directly); `tm.r1` broker note on profit definitions (IFRS net income and adjusted net income by
business; a forecast); `tm.r2` broker note on underwriting, reserves, growth and capital allocation; `tm.r3` broker
note on the stock split; `tm.r4` to `tm.r7` further broker notes (an acquisition note, two stock reports, a note on
risks), `tm.r8` a quantitative rating report (searched only); `tm.corpus` the whole supplied corpus as a search scope;
`tm.pub` public business and accounting knowledge. The company document pack of Oct 18 adds `tm.pk.*` ids, one per
document (below).

## Plan round and the pack

The reviewer's build plan (Oct 18) set eleven areas, in the order composition, operating paths, financial mapping,
calibration; the company's own document pack arrived mid-round and was read before anything was sized. The pack is
client data: its inventory, passages, levels and figures stay local under `data/sally_data/construction/tokio_marine/`
(`pack_inventory.md`, `sources.json`, `citations.json`, `baselines.json`, `baselines_quarterly.json`,
`validation.json`). This section holds ids, structure, methods and counts only.

**Source inventory.** The pack came without a manifest: 150 files in three groups, 144 distinct documents once
byte-identical copies are folded. Each document has a neutral id `tm.pk.<kind>_<date>` in the local `sources.json`
with its file, kind, date, accounting basis, folder and read state. Kinds: annual securities reports (two, Japanese),
quarterly summary reports, results presentations, quarterly data workbooks, IFRS group data workbooks, Japan P&C
subsidiary J-GAAP workbooks, major-subsidiary results, solvency releases and the solvency-sensitivity chart, embedded
value releases, managed-asset factsheets, strategy and investor-day decks, integrated reports, share repurchase,
dividend and stock-split notices, rating reports, and monthly premium workbooks (not parsed: unsupported format). The
pack was parsed with the repository parser under `python -I`; nothing in it was executed.

### Part 1: before and after audit by canonical id

| Object | Before the round | After | Added | Removed or renamed |
|---|---|---|---|---|
| values (`subentities`) | 69 | 118 | 58 | 9 renamed off common words (R2/KEYWORD), e.g. `jpc_tax_other` → `jpc_tax_and_adjustments`, `tmnf_rate_level` → `tmnf_renewal_rate` |
| links in this file | 102 | 159 | 57 | none; 15 retargeted (below) |
| compositions | 10 | 16 | `net_income_bridge`, `jpc_assets_by_class`, `jpc_yen_bond_ladder` (reconciling), `jpc_cash_sources`, `international_regions` (reconciling), `group_debt_cash_flows` (reconciling) | none |
| identities | 1 | 10 | `jpc_gross_income`, `jpc_hedge_cost`, `jpc_new_money`, four allocation products, `jpc_uw`, `adjusted_eps`; `jpc_nii` redefined | none |
| stock-flows | 2 | 6 | `jpc_yen_bonds`, `jpc_foreign_hedged`, `jpc_foreign_unhedged`, `jpc_nonbond`; `parent_capital` now has one inflow | none |
| paths | 14 | 18 | `domestic_dividends`, `japan_life_rates`, `japan_life_lapse`, `per_share` | none; five rewritten |

| Area | Owned before | Built or changed (canonical ids) | State |
|---|---|---|---|
| 1 Metric ambiguity (R2) | `operating_profit` (adjusted net income), J-GAAP segments | `net_income_ifrs`, `ani_to_ni_adjustments`, `tm.comp.net_income_bridge`; a label-target test | built and verified |
| 2 Composition by business | ANI by business, Japan P&C and international views | `domestic_subsidiary_dividends`, `japan_life_new_business`, `solution_revenue`, `tm.path.domestic_dividends` | built; dividends bound to the holding company's total (proxy) |
| 3 Reinvestment | one product identity, sign-only steps | redemptions → cash freed less cash held back (`tm.comp.jpc_cash_sources`) → deployed share → allocation by class, currency and hedge (four product identities) → class stocks (four stock-flows) → income = assets x yield → net of investment expenses; ladder as a reconciling view | built; redemption entry unsized (no Japan P&C ladder) |
| 4 Underwriting and repricing | links straight into insurance-related profit | `tm.id.jpc_uw`: insurance-related profit = insurance revenue - claims incurred - expenses; catastrophe, severity, loss-ratio and US-reserve links retargeted to claims, earned premium and ceded cost to revenue; exposure → claims | built and bound (the identity reconciles at the pack levels) |
| 5 International and FX | local profit, translation, unit view | `tm.comp.international_regions` (reconciling), regional values and `intl_ani_unallocated` | built and bound |
| 6 Liabilities and accounting | asset and liability marks to ESR | `tm-c-liability-oci-equity` (parallel OCI route), `tm-c-spread-esr`, `tm-c-fx-esr`, `credit_spread_portfolio` | built; equity, FX and spread routes sized |
| 7 Reserve and catastrophe shocks | sign-only catastrophe and reserve links | catastrophe losses into claims one for one; `jpc_reinsurance_recoveries` with `tm-c-cat-recoveries` (threshold, retention not disclosed) and `tm-c-recoveries-claims`; dated reserve and catastrophe events (local) | built; recoveries unsized |
| 8 Disposal and distribution | sale → book, dividends, ESR, capital | `cross_holding_realized_gains`, `tm-c-sale-gains`, `tm-c-gains-segment` (J-GAAP only); `tm-c-sale-capital` now funds subsidiary dividends; `tm-c-remit-capital` routes remittances through them (R13) | built; equity marks sized |
| 9 Japan Life and per share | Japan Life profit only | `japan_life_ev`, `japan_life_lapse_rate`, `tm-c-jgb-ev`, `tm-c-lapse-ev`, `tm-c-lapse-life`, `tm-c-newbiz-ev`; `shares_outstanding`, `adjusted_eps` (`tm.id.adjusted_eps`), `dps`, `tm-c-returns-shares`, `tm-c-eps-dps`; the split as a dated corporate action | built; EV links sized |
| 10 Validation cases | none | three cases in the test module, in both worlds | built and verified |
| 11 This section | earlier rounds | four parts and the checklist | done |

Retargeted links (same ids): `tm-c-premium-earned`, `tm-c-reins-profit` (to insurance revenue); `tm-c-cat-profit`,
`tm-c-severity-reserves`, `tm-c-loss-profit`, `tm-c-tmnf-usliab-profit` (to claims incurred); `tm-c-portfolio-cash`
(to redemptions); `tm-i-jpc-nii-assets`, `tm-i-jpc-nii-yield` (to gross income); `tm-c-hedge-nii` (to the hedge-cost
amount); `tm-c-sale-capital`, `tm-c-remit-capital` (to subsidiary dividends). `tm-i-jpc-nii-hedge` (added and removed in
this round) became `tm-a-hedge-financial`.

### Part 2: composition and paths

- **Japan P&C, one IFRS basis, three layers.** Insurance-related profit is an identity of revenue, claims and expenses;
  financial-related profit is net investment income, the liability unwind and other financial items; adjusted net
  income adds taxes and adjustments (a stated residual). Net investment income is interest and dividends less
  investment expenses: the company's IFRS breakdown has no hedge line inside it, so the hedge cost on hedged foreign
  bonds is charged to other financial items (`tm-a-hedge-financial`, an inference the inputs table states).
- **Reinvestment never applies a market yield to the whole book.** New-money yields act only on the money reinvested
  (`tm-c-invest-income`, a sign flip at the book yield), through allocation identities and class stocks; the tests
  assert no market-yield link reaches the yield, income or portfolio.
- **Scope is explicit.** The pack's maturity table is group scope (every segment and currency, undiscounted principal
  and coupons) and is held as its own reconciling view; it never sizes Japan P&C redemptions. The Japan Life
  subsidiary's maturity schedule is another scope again. The hedge-accounting forwards in the notes hedge net
  investments in foreign operations (translation, through OCI), not the hedged foreign-bond slice.
- **Parent resources.** Overseas companies are held by the Japan P&C subsidiary, so their remittances reach the holding
  company inside that subsidiary's dividend: parent capital has one inflow (R13).
- **Disposal.** Under IFRS a business-related equity sale moves the gain within equity; it reaches J-GAAP segment profit
  of the seller, never IFRS net income or adjusted net income. Cash reaches the parent as subsidiary dividends, then
  returns or acquisitions.
- **Japan Life.** Embedded value and IFRS profit are parallel measures of one shock (`tm.path.japan_life_rates`,
  `tm.path.japan_life_lapse`); they are never added.
- **Per share.** Adjusted EPS = 1000 x adjusted net income / shares outstanding (ratio identity). The company's EPS uses
  average shares, so the identity on period-end shares differs slightly; the EPS level is left unbound rather than
  forced. The stock split is a dated corporate action; per-share and share-count series are not converted across it.

### Part 3: evidence and calibration

**Inputs before → after** (Tokio Marine's own inputs, `check.py`): found and connected 11 → 11; found, not connected
3 → 13; found as a proxy 0 → 5; disclosed but not supplied 3 → 0; not disclosed in the reviewed sources 27 → 16; not yet
reviewed 0 → 0. The pack search (`inputs.py --corpus <pack>`) added Japanese queries per input (for example 償還予定額
and 満期分析 for the ladder, ヘッジ手段 and 為替予約 for hedges, 再保険 for reinsurance, クレーム・ディベロップメント for
triangles, 関係会社受取配当金 for subsidiary dividends); every candidate was read before a status moved.

**Securities-report tables read first** (Japanese label, translation, scope):

| Label | Translation | Scope | Use |
|---|---|---|---|
| 金融商品の満期分析 / 投資有価証券（負債性） | maturity analysis of financial instruments / investment securities (debt) | group, all currencies, undiscounted cash flows | `tm.comp.group_debt_cash_flows`; Japan P&C ladder stays unsized |
| 市場リスクに関する感応度分析 (金利 / 為替 / 株式) | market-risk sensitivity (rates / FX / equities) on pre-tax profit, OCI and equity | group, financial instruments and insurance contracts together | equity row sizes `tm-c-xholding-equity`; rate row is a net check; FX row excludes translation of foreign operations, so not used |
| ヘッジ会計: 在外営業活動体に対する純投資ヘッジ | hedge accounting: net investment hedges of foreign operations | group | not the bond-hedge slice (R14); input stays found, not connected |
| 関係会社受取配当金 | dividends received from affiliates (holding company, J-GAAP) | holding company | `domestic_subsidiary_dividends` level |
| 保険契約の満期分析; クレーム・ディベロップメント | insurance-contract maturity analysis; claims development | by segment | found, not bound |

**Calibrations** (`scripts/construction/calibrate.py`, written into the file; figures local):

| Link | Disclosure (source id) | Method | Scope note |
|---|---|---|---|
| `tm-c-xholding-esr` | solvency sensitivity chart (`tm.pk.esr_sensitivity_ch_20260331`) | `--disclosure`, jointly with the FX and spread links, split by direction, sign flipped (the ratio rises when equities fall) | the shock moves all listed equities; sized per 30% move of the book |
| `tm-c-fx-esr` | same | same, asymmetric | the shock moves all currencies; USD/JPY stands for them |
| `tm-c-spread-esr` | same | same, asymmetric | spreads on its own credit holdings (`credit_spread_portfolio`, an exogenous hook) |
| `tm-c-jgb-ev` | embedded value release (`tm.pk.embedded_value_rel_20260522`) | `--disclosure`, jointly with lapse, split by direction | parallel risk-free shift; JGB 30Y stands for the yen curve |
| `tm-c-lapse-ev` | same | same | lapse rates x 1.1 as +10 on the index |
| `tm-c-cat-profit` | IFRS group data (`tm.pk.ifrs_data_20260520`) | one for one (`--source-change 1 --target-change 1`) | catastrophe impact sits inside incurred losses |
| `tm-c-xholding-equity` | securities report (`tm.pk.yuho_fy2025`) | sensitivity, per 10% move of the book | the disclosure covers all listed equities, after tax |

Not sized, and why: the rate shock on the solvency ratio and on equity (net of two parallel marks; neither branch can
be sized alone), recoveries (retention not disclosed), redemptions (no Japan P&C ladder), allocation and deployment
(not disclosed), lapse into IFRS profit (the CSM absorbs assumption changes first), buybacks into share count (one
value holds dividends and buybacks together).

**Baselines.** FY3/26 levels from the pack were added for the underwriting identity, gross income and investment
expenses, the regional view, the group debt cash flows, parent dividends received, embedded value, disposals and
realized gains, shares and DPS (21 items). The two Japan P&C levels the second round had derived (insurance-related
profit and its taxes-and-adjustments residual) were replaced by the reported figure and the residual it implies.
Guidance stays out of the baselines (R8): the FY3/27 plan is a dated guidance event. Ratings are third-party views and
size nothing. **Dated series:** eight standalone quarters (FY3/25 Q2 to FY3/27 Q1) for eleven Japan P&C subsidiary values
(J-GAAP, one basis throughout), derived from cumulative figures (loss ratio from cumulative incurred and cumulative
ratio), annualized in the value's unit; IFRS group points for the quarters the company reports on IFRS; IFRS adoption
(April 2025) as an explicit break; reserve, catastrophe, capital-action and split events with dates
(`baselines_quarterly.json`, kept apart from `baselines.json` so the annual levels stay the reconciling set).

### Part 4: end-to-end checks

- **Reconciliation at the pack levels** (`check.py --reconcile --baselines`): 12 of 15 additive views reconcile; 3 are
  blocked by levels the pack does not give at Japan P&C scope (class balances, cash sources, the yen ladder); 0 flags.
  Identities: underwriting, gross income and net investment income reconcile; 7 are blocked (no level for allocation,
  hedge notional or EPS on the identity's basis). At the model medians all 15 views and 10 identities reconcile.
- **Coverage of own steps.** Links in this file: 70 of 159 carry a size (identities, stock-flows, accounting weights,
  calibrated links). Path steps: 69 of 136 sized; fully sized: overseas translation; the asset-marks path is the
  unsized one (rates).
- **Validation cases** (`tests/scenario/test_construction_tokio_marine.py`, in sally_demo and sally_focus, through
  the model, the v4 export and the construction trace):
  1. *Reinvestment uplift against underwriting deterioration.* The book income yield up 0.1pt and claims up ¥20bn on
     the model's synthetic levels: by hand gross income +6.4, insurance-related profit -20, Japan P&C profit negative.
     The model carries both through the identities within a band (forecasts sample their effects) and uses no market
     yield on the whole book.
  2. *Asset marks against solvency.* A 30% fall in the equity book: the ratio rises (the disclosed sign flip), equity
     falls through OCI, adjusted net income is unchanged; with the local folder, the ratio change is checked against the
     disclosure. A 50bp rate rise: embedded value moves by its disclosed sensitivity (local check), while the solvency
     ratio stays unmoved because both mark branches are unsized, and the forecast says so.
  3. *A catastrophe outside both.* ¥50bn of domestic catastrophe losses: claims up, insurance-related profit down by
     the same amount (identity), Japan P&C and group profit lower; recoveries are listed as uncalibrated.

### Pack checklist

| Step | Done | Where |
|---|---|---|
| Inventory without a manifest; neutral ids; duplicates folded | yes | local `pack_inventory.md`, `sources.json` |
| Input search over the pack with Japanese queries; candidates read; statuses moved | yes | local `input_search.*` under the pack folder; statuses in the file |
| Securities-report tables first, labels with translations, scope checked | yes | Part 3 |
| FY3/26 levels; derived levels replaced by reported ones | yes | local `baselines.json` |
| Eight standalone quarters; IFRS adoption as a break | yes | local `baselines_quarterly.json` |
| Guidance apart from actuals (R8); ratings as views | yes | dated events |
| Solvency, embedded value, catastrophe, disposal, buyback, dividend and split disclosures | sized where a link matches the measure; otherwise held as levels, events or checks | Part 3 |
| Validation cases through the model, export and context | yes | test module |

Still to ask for: the Japan P&C yen-bond redemption schedule (by currency and hedge status), the hedged notional on
foreign bonds and its cost line under IFRS, the catastrophe reinsurance retention, the allocation of new money, and
the solvency sensitivity split between assets and liabilities.

## Gap register

Written before the model was changed. "Internal" is the loaded sally_demo graph and its YAML; "export" is the v4.1.4
pack the reviewer inspected (036, state version 432). Categories: **MC** missing construction, **CAL** missing
calibration, **MAP** incorrect mapping, **EXP** export omission, **RET** retrieval omission. Outcome codes (filled in
the [completion report](#completion-report)): built and verified / built but uncalibrated / blocked by a named input /
not built.

| # | Gap (missing or incorrect structure) | Present now (internal / export) | Add or correct | Evidence or input needed | Conclusions affected | Test that shows it done | Cat. |
|---|---|---|---|---|---|---|---|
| G01 | Group profit definition clash: `tokio_marine.operating_profit` is named adjusted net income but exported as metric `operating_profit`; m22/m23 aggregate two businesses into it with statistical weights and no other parts | Internal: value with no basis; m22, m23 causal, calibrated "adds to". Export: E69_FIRM_FINANCIALS and E69_FIRM_FINANCIALS__OPERATING_PROFIT target `operating_profit` | `features.metric: adjusted_net_income` and `features.basis`; m22/m23 become accounting links on one basis (adjusted net income by business, company definition); add Japan Life, solution/other and consolidation-adjustment parts | Company's adjusted-net-income-by-business definition (`tm.seg`, `tm.r1`) | Any group-profit sum; share of group from international; FX and rate effects on group profit | `test_adjusted_net_income_view_reconciles`, `test_export_names_metrics_by_definition` | MAP |
| G02 | Workbook reportable-segment profit (domestic non-life, domestic life, international, financial/other, adjustments) not represented; at risk of being read as adjusted net income | Internal: none. Export: none | Separate composition on its own basis (J-GAAP segment profit), never added to the adjusted-net-income view | Workbook segment rows (`tm.wb`) | Segment mix and growth history; any J-GAAP-to-IFRS comparison | `test_segment_profit_view_is_separate_and_reconciles` | MC |
| G03 | Statutory (IFRS) net income to adjusted net income bridge | Internal: none. Export: none | Not an identity at this granularity: company adjustment items (reserve provisions, equity-sale gains, amortization, one-offs) are not split by business in the sources read | Company reconciliation table by business | Statutory EPS, payout ratio on net income | gap stays visible: no link from any statutory value to `operating_profit` | MC |
| G04 | Japan P&C composition: insurance-related versus financial-related profit; investment income versus liability unwind | Internal: `japan_pc_profit` single value. Export: same | Composition `tm.comp.japan_pc_ani` (insurance profit, financial-related profit, tax/other) and `tm.comp.japan_pc_financial` (net investment income, insurance finance expense, other) | `tm.seg` financial-related profit lines (cited company pages) | Whether a yield rise reaches Japan P&C profit and by how much after the unwind | `test_required_compositions_exist`, `test_composition_parts_have_accounting_links` | MC |
| G05 | International operations: local operating growth versus yen translation; underwriting versus investment; distinct businesses | Internal: `international_profit` with four broad driver links (m19, m20, s41, s55). Export: same | Local-currency international profit with its own composition, an accounting translation link to the yen value, and a business-unit view (three US units and residual) | `tm.seg` (insurance/financial split, plan rate), `tm.wb` business-unit profits | Overseas share, FX sensitivity, "overseas is homogeneous" | `test_international_local_and_translation_are_separate` | MC |
| G06 | Underwriting units (Japan P&C lines; compulsory auto as a no-profit line) | Internal: none | Composition `tm.comp.tmnf_lines` | `tm.wb` premiums by line | Premium growth decomposition; claims-inflation exposure by line | `test_required_compositions_exist` | MC |
| G07 | Investment assets: what earns, by asset class; balances, maturity ladder, currency and hedge notional | Internal: none. Export: none | Income by asset class composition `tm.comp.tmnf_income_by_asset` (supported); balances only where disclosed; no maturity ladder | Maturity ladder, reinvestable cash flows, hedge notional and ratio (not disclosed in the sources read) | Size of any reinvestment uplift; JGB vs UST scope | `test_no_invented_ladder`, reinvestment steps uncalibrated | MC / CAL |
| G08 | Reinvestment as six connected transitions (existing assets → eligible cash → chosen investments → earned income → net investment result → segment profit → group earnings and capacity) | Internal: none (only m20, m21 direct yield → profit). Export: PATH_TOKIO_MARINE_JAPANESE_INSURERS_REINVESTMENT groups 13 string steps across two insurers | Path `tm.path.reinvestment` with a canonical link per stage | Maturity ladder, turnover, allocation, actual new-money yields (blocked for size) | Every "higher yields help" conclusion | `test_reinvestment_has_its_six_transitions` | MC / CAL |
| G09 | Broad yield links assume a market yield applies to a whole book (m21: JGB 30Y → Japan P&C; m20: UST 10Y → international) | Internal: calibrated, no scope statement; the J-GAAP income split shows domestic bond income is a small part of Japan P&C interest and dividends | Keep ids and sizes (statistical records, Sally's expected paths); add transitions stating scope, that they are reduced-form summaries of the structural paths and must never be added to them; flag m21's size as unsupported by asset-level scope | Asset-level scope (G07) to recalibrate | JGB-driven Japan P&C upside | `test_broad_yield_links_state_their_scope` | MAP / CAL |
| G10 | FX hedge cost on foreign bonds | Internal: none | `tokio_marine.fx_hedge_cost` from the US–Japan short-rate gap into Japan P&C net investment income | Hedge notional and ratio (not disclosed) | Net benefit of foreign yields to Japan P&C | path `tm.path.fx_hedge_cost` | MC / CAL |
| G11 | Asset marks and liability valuation as parallel routes to equity and solvency, not subtracted from recurring income | Internal: none | `tm.path.asset_marks_liabilities`, `tm.path.equity_marks` ending at solvency/net assets, with no link into adjusted net income | ESR sensitivities by shock (disclosed but not mappable from the source read) | Solvency and book-value effects of rate moves | `test_marks_never_reach_recurring_income` | MC / CAL |
| G12 | Claims inflation, repricing, retention | Internal: none | `tm.path.claims_inflation_repricing`, `tm.path.policy_growth` | Severity indices, rate filings, retention (not in sources read) | Japan P&C margin path | `test_required_paths_exist` | MC / CAL |
| G13 | Reserve development (US liability), catastrophes, reinsurance | Internal: none | `tm.path.us_liability_reserves`, `tm.path.catastrophe_reinsurance` | Reserve triangles, cat budget versus actual, reinsurance programme | Japan P&C and international insurance profit | `test_required_paths_exist` | MC / CAL |
| G14 | Overseas translation with its counter-effect (foreign-currency claims reserves in Japan P&C) | Internal: m19 only (size not tied to a disclosure) | `tm.path.overseas_translation`; calibrated reserve link from the company's disclosed per-yen sensitivity; m19 cross-checked against the same disclosure | Company FX sensitivity (`tm.co` via `tm.seg`) | Net group FX sensitivity; "overseas share equals FX sensitivity" | `test_fx_counter_effect_is_calibrated_from_disclosure` | MC |
| G15 | Cross-holding disposal: proceeds and realized gains are not recurring income | Internal: none | `tm.path.cross_holding_disposal`: forgone dividends (recurring, negative), capital and risk release, redeployment | Sale programme and book (company plan cited in `tm.seg`) | Payout and M&A capacity; ANI growth | `test_cross_holding_proceeds_never_reach_recurring_income` | MC |
| G16 | Capital and allocation (solvency, excess capital, remittances, payout, acquisitions) | Internal: none | Values and `tm.path.capital_payout`; non-additive view `tm.comp.capital_sources_uses` | Parent cash and remittance data | Any dividend or buyback conclusion | `test_required_paths_exist` | MC / CAL |
| G17 | Growth execution (acquisitions; organic specialty growth) | Internal: none | `tm.path.growth_execution` | Deal terms, financing, integration | Inorganic earnings growth | `test_required_paths_exist` | MC / CAL |
| G18 | Policy growth (exposure → premium → earned result) | Internal: none | `tm.path.policy_growth` | Exposure and quote data | Premium growth versus profit | `test_required_paths_exist` | MC / CAL |
| G19 | Transitions, compositions and named paths absent from the inspected export | Export: none (not represented in the inspected export) | Export carries them: transitions in relationship properties, `financial_bridge`, `business_construction` paths, `schema_gaps` | none | Downstream agent context | `test_new_objects_reach_the_export` | EXP |
| G20 | New node ids not retrievable through the service | Internal API: values not yet present | `/v1/world-models/sally_demo/graph` and `…/entities/tokio_marine/construction` serve them | none | Agent retrieval | `test_new_objects_reach_the_api` | RET |
| G21 | Per-share normalization after the 15-for-1 split (a split is not operating growth) | Internal: `tokio_marine.share_price` level is pre-split | Not built here: the split must be declared so post-split prices are not read as a 93% fall (the import rule exists: [README](README.md#declare-a-stock-split)) | Split ratio and effective date, declared as a corporate action on `tokio_marine` | Share-price signals after the split date | listed as blocked | MAP |
| G22 | Shared insurer path in the export groups parallel responses of two insurers | Export: PATH_TOKIO_MARINE_JAPANESE_INSURERS_REINVESTMENT (a generated leaf-configuration chain) | Do not touch the shared path; add company-specific named paths beside it | none | Path resolution | business paths exported with `path_kind: business_construction` | EXP |

## Audit before modifying

| Requirement or object | Class | Controlling object | Action |
|---|---|---|---|
| Identity, aliases, memberships, kind defaults (`tokio_marine`, share price) | Already owned | entities.yaml `tokio_marine` | aliases untouched; description adjusted to scope the yield claim |
| Broad FX and yield relations m19, m20, m21, s41, s55, s70 | Already owned (statistical records) | interactions.yaml | ids and sizes kept; transitions added (Modify lightly) |
| m22, m23 aggregation | Modify lightly | interactions.yaml | accounting links on the adjusted-net-income basis, weights from scales |
| `operating_profit`, `international_profit`, `japan_pc_profit` definitions | Modify lightly | entities.yaml | `features.view/basis/metric` added; ids kept for Sally's expected paths |
| Compositions, intermediate decisions, connected financial conversion, workbook bindings | Missing | construction/tokio_marine.yaml; local sources.json and baselines.json | built |
| Shared insurer export path, MS&AD objects, shared governance | Do not touch | export generator; msad entity | untouched |

## Definitions and bases

- **Adjusted net income by business** (`features.basis` on `operating_profit` and its parts): the company's own
  definition, IFRS from the fiscal year ending March 2027, which excludes gains on business-related equities (they
  go to OCI under IFRS). Parts: international, Japan P&C, Japan Life, solution/other, consolidation adjustment. Exported
  metrics: `adjusted_net_income`, `international_adjusted_net_income`, `japan_pc_adjusted_net_income`, ...
- **Reportable-segment profit** (J-GAAP, history through March 2026): domestic non-life, domestic life, international,
  financial/other, adjustments. Pre-tax, ordinary-profit based. A different basis and perimeter: never added to, or
  equated with, adjusted net income.
- **Business-unit profit by international unit** (pre-IFRS company basis): the three US units and a residual. Its
  bridge to the IFRS international value is a definitional, uncalibrated link.
- **Japan P&C lines and investment income by asset class** (J-GAAP, the main P&C company, non-consolidated): operating
  detail that explains the IFRS business; bridged to IFRS net investment income by an uncalibrated link (dividends
  from overseas subsidiaries are eliminated on consolidation).
- **Local-currency international profit** (USD-equivalent at the company's plan rate): the yen value is local profit
  times the reporting rate, so `tm-a-intl-translate` is an accounting conversion and m19 carries the rate.

## Second review round

The reviewer's second round (Oct 18) found five things missing from this build. Each is now checked by a script
([methods](README.md)) and by `tests/scenario/test_construction_tokio_marine.py`. The client-side evidence (passages,
cells, levels, search reports) stays local under `data/sally_data/construction/tokio_marine/`.

| # | Finding | What was done | Where it is checked |
|---|---|---|---|
| 1 | Source labels did not resolve to a document and a passage | `sources.json` gives each of 13 source ids its file, kind, date, period, basis, read state and proof limits. Ids `tm.r4` to `tm.r8` and `tm.corpus` were added for the files searched. `citations.json` gives every material claim (82 links) and every baseline value (48) a source id, an exact location (sheet and cells, or page and lines) and the verbatim passage. Each link's cited ids are also in its `evidence.sources` | `check.py --sources`: 10 cited ids resolve, 0 do not, 0 material claims without a citation |
| 2 | Missing inputs did not say whether the material was searched | Every `transition.unresolved` entry is an input with a status. 35 distinct inputs: 9 found and connected, 2 found but not connected, 24 not disclosed in the reviewed sources, 0 not yet reviewed. Each not-disclosed input lists the source ids and queries it was searched with. The search ran twice: on Tokio Marine's own files and on the whole corpus (180 files). Every candidate was read (local `inputs_review.md`) | `check.py`: inputs by status; the test fails on any `not_yet_reviewed` |
| 3 | The numbers did not satisfy the stated relationships | Synthetic round priors now add up at the medians in all 9 additive views, with each residual's basis saying it closes the round parts to the round total. The accounting weights the new levels imply were updated. At the FY3/26 baselines the two missing Japan P&C levels were added, and the taxes-and-other residual is stated as the explicit unexplained difference | `check.py --reconcile --statistic median` and `--baselines`: 0 flags |
| 4 | No account of what a forecast's numbers are made of | For each path and for the generalization trace: the calibrated, accounting and uncalibrated steps, the inputs that block a size, and a forecast's `coverage` (contributed links, routes fully quantified) beside `context.construction.trace` | [Calculation coverage](#calculation-coverage) |
| 5 | The method must generalize | The same process as the first round, now including citations, searched inputs, reconciliation and coverage. No new calibration: the material holds no disclosed sensitivity that maps onto an uncalibrated link (see below) | this page; the test module |

### Inputs by status

(Superseded by the [plan round](#part-3-evidence-and-calibration): the company pack has maturity tables, at group and Japan Life scope only.)
**The maturity answer, plainly: Tokio Marine's maturity information is not disclosed in the supplied material. It was
searched for, and the search found nothing to extract.** No maturity ladder, redemption schedule, average life or
portfolio duration exists for any Tokio Marine portfolio in any of these:

- the sell-side workbook (`tm.wb`): every tab, read cell by cell and parsed;
- the eight broker notes (`tm.r1` to `tm.r8`): every page;
- the client segment model (`tm.seg`), whose own list of items the company does not disclose names portfolio duration
  and reinvestment cash flows.

The reinvested shares that model uses are its own assumptions, marked as such, and are not used here. Across the whole
corpus (`tm.corpus`), every hit for maturity, ladder, redemption or duration concerns other companies, or the
disclaimer sense of "duration". The company's own disclosures are not among the supplied files. The model cites them
by page, and none of the cited pages is a maturity page.

What the search did find is bound as found and connected, with what it cannot do stated:

- Group-wide annual purchases, sales and redemptions of securities from the consolidated cash flow. Sales and
  redemptions are combined, and nothing is split by business, asset class or maturity. This is an upper bound on
  turnover, not a ladder.
- The Japan P&C, Japan Life and North America portfolio sizes and average income yields.

In the model, `tm-c-portfolio-cash` carries "maturity ladder" as not disclosed in the reviewed sources. No ladder value
exists (`test_no_invented_ladder`). The reinvestment steps stay uncalibrated.

| Status | Input | Links | Found in |
|---|---|---|---|
| found_connected | annual securities purchases, sales and redemptions (consolidated cash flow) | `tm-c-portfolio-cash` | tm.wb |
| found_connected | basis of the disclosed FX sensitivity (J-GAAP or IFRS adjusted) | `tm-c-fx-reserves` | tm.seg |
| found_connected | company per-yen FX sensitivity of overseas profit | `m19` | tm.seg |
| found_connected | FX hedging cost, J-GAAP, latest quarter | `tm-c-hedge-nii` | tm.seg |
| found_connected | Japan Life investment assets and income yield | `tm-c-jgb30-life` | tm.seg |
| found_connected | Japan P&C investment assets and income yield | `tm-c-portfolio-cash` | tm.seg |
| found_connected | natural catastrophe budget versus actual | `tm-c-cat-profit` | tm.r1, tm.seg, tm.wb |
| found_connected | North America investment assets and income yield | `tm-c-intl-portfolio-income` | tm.seg |
| found_connected | US liability reserve additions (amounts) | `tm-c-tmnf-usliab-profit` | tm.r2, tm.r6 |
| found_not_connected | net asset sensitivity to yen rates | `tm-c-jgb-bondmark` | tm.seg |
| found_not_connected | net premium cash flow (Japan P&C) | `tm-c-portfolio-cash` | tm.wb |
| not_disclosed_in_reviewed_sources | allocation of new money by asset class, currency and tenor | `tm-c-cash-invest` | - |
| not_disclosed_in_reviewed_sources | bond holdings by accounting classification and duration | `tm-c-jgb-bondmark` | - |
| not_disclosed_in_reviewed_sources | cohort sizes of maturing assets | `tm-c-invest-income` | - |
| not_disclosed_in_reviewed_sources | discount-rate locking by cohort | `tm-c-jgb30-ife` | - |
| not_disclosed_in_reviewed_sources | ESR sensitivity to interest rates by shock | `tm-c-jgb-liability` | - |
| not_disclosed_in_reviewed_sources | European investment assets and turnover | `s41` | - |
| not_disclosed_in_reviewed_sources | floating-rate share (North America) | `m20`, `tm-c-intl-nmy-income` | - |
| not_disclosed_in_reviewed_sources | FX hedge notional and hedge ratio | `tm-c-hedge-nii` | - |
| not_disclosed_in_reviewed_sources | IFRS insurance revenue by line | `tm-c-premium-earned` | - |
| not_disclosed_in_reviewed_sources | IFRS insurance service result by line | `tm-c-loss-profit` | - |
| not_disclosed_in_reviewed_sources | IFRS investment income by asset class | `tm-c-jtd-nii` | - |
| not_disclosed_in_reviewed_sources | IFRS line of the hedge cost | `tm-c-hedge-nii` | - |
| not_disclosed_in_reviewed_sources | IFRS split by international unit | `tm-c-bup-bridge` | - |
| not_disclosed_in_reviewed_sources | insured exposure by line | `tm-c-exposure` | - |
| not_disclosed_in_reviewed_sources | maturity ladder | `tm-c-portfolio-cash` | - |
| not_disclosed_in_reviewed_sources | reinsurance recoveries and ceded cost by business | `tm-c-reins-profit` | - |
| not_disclosed_in_reviewed_sources | reinvested share per year (Japan Life) | `tm-c-jgb30-life` | - |
| not_disclosed_in_reviewed_sources | reinvested share per year (Japan P&C) | `m21`, `tm-c-nmy-income` | - |
| not_disclosed_in_reviewed_sources | reinvested share per year (North America) | `m20`, `tm-c-intl-nmy-income` | - |
| not_disclosed_in_reviewed_sources | reserve triangles | `tm-c-severity-reserves` | - |
| not_disclosed_in_reviewed_sources | settlement pattern by line | `tm-c-severity-reserves` | - |
| not_disclosed_in_reviewed_sources | tenor mix of new purchases (Japan P&C) | `m21`, `tm-c-jgb30-nmy` | - |
| not_disclosed_in_reviewed_sources | turnover by asset class | `tm-c-portfolio-cash` | - |
| not_disclosed_in_reviewed_sources | yield of maturing assets | `tm-c-invest-income` | - |

Counts (distinct inputs): found_connected 9, found_not_connected 2, not_disclosed_in_reviewed_sources 24, not_yet_reviewed 0.

Found and connected means the input is bound by a citation, a baseline observe or both. It is not a sensitivity, so a
link that lists one can still have no size. The two found but not connected inputs are found in a form that cannot be
bound to the link:

- The net asset sensitivity to yen rates is for Japan Life only. It nets the asset and liability marks, so it cannot
  size the asset-only mark.
- The only cash flow found is the group's consolidated operating cash flow. It is not Japan P&C's net premium cash flow.

**Why nothing new is calibrated.** `scripts/construction/calibrate.py` needs a disclosed sensitivity of a link's target
to its source. The material holds the per-yen FX sensitivity, which is already used (`tm-c-fx-reserves`, with `m19`
consistent). It also holds the Japan Life net asset sensitivity, which nets two parallel links. The client model's
per-basis-point sensitivities rest on its own reinvestment and liability-offset assumptions. None of these maps onto an
uncalibrated link without an assumption.

### Reconciliation

Each additive view is checked as total = members + residual + eliminations, within 0.5% of the total, in one unit.
This page gives the structure and the relative differences only. The levels are local (`reconciliation.md`).

| Composition | Parts (sign) | Residual / eliminations | Priors at medians | FY3/26 baselines |
|---|---|---|---|---|
| `tm.comp.ani_by_business` | international, Japan P&C, Japan Life, solution (+) | eliminations: consolidation adjustment | +0.00% ok | +0.00% ok |
| `tm.comp.japan_pc_ani` | insurance-related, financial-related (+) | residual: taxes and other | +0.00% ok | +0.00% ok; insurance-related profit is derived and taxes and other is the explicit unexplained difference (below) |
| `tm.comp.japan_pc_financial` | net investment income, insurance finance expense (negative level) | residual: other financial items | +0.00% ok | -0.00% ok |
| `tm.comp.international_local` | insurance-related, financial-related (+) | residual: taxes and other | +0.00% ok | +0.00% ok |
| `tm.comp.international_financial` | net investment income, insurance finance expense (negative level) | residual: other financial items | +0.00% ok | +0.04% ok (rounding of the currency conversion) |
| `tm.comp.international_units` | three US units (+) | residual: other units | +0.00% ok | +0.00% ok |
| `tm.comp.jgaap_segments` | four reportable segments (+) | eliminations: adjustments | +0.00% ok | -0.00% ok |
| `tm.comp.tmnf_income_by_asset` | four asset classes (+) | residual: other interest and dividends | +0.00% ok | +0.00% ok |
| `tm.comp.tmnf_lines` | fire, voluntary auto, marine and specialty (+) | residual: compulsory auto liability | -0.00% ok | +0.00% ok |

- **Priors.** These synthetic round levels were changed: Japan Life, solution, Japan P&C and international taxes and
  other, the other-units residual, segment adjustments, voluntary auto premiums, and the P&C company's interest and
  dividends total and its residual. The accounting weights of `tm-a-ani-life`, `tm-a-ani-solution`, `tm-a-npw-auto`,
  `tm-a-inc-domeq` and `tm-a-inc-foreq` follow from them. Shared values (`operating_profit`, `international_profit`,
  `japan_pc_profit`) and Sally's expected paths are unchanged.
- **Means.** At the posterior means 7 of 9 views are within tolerance. Japan P&C financial-related profit and the P&C
  company's income by asset class are not. The mean of a lognormal part is its median times exp(sigma^2 / 2), so round
  levels that add up at the medians cannot also add up at the means ([README](README.md#reconciliation)).
- **Unexplained difference.** No supplied source reports Japan P&C insurance-related profit. The baseline derives it as
  a broker's IFRS non-life insurance-related profit less the company's international insurance-related profit. The
  taxes-and-other residual closes the view and is labelled the unexplained difference. It is about a sixth of Japan P&C
  adjusted net income, and its rate on pre-tax profit is well below the international business's. Treat the derived
  split as weak: it is an input to replace when the company's Japan P&C insurance-related profit is read.

### Calculation coverage

Each row comes from a forecast of a +1 sd move in the path's first value, with a 365-day horizon. The targets are the
path's endpoint and the group totals. The row also gives `context.construction.trace` from the same value. "Routes"
are simple paths of at most six links from the shock to the endpoint. A route is fully quantified when every link on
it has a size. The calculated size comes only from the links named in the forecast column. Every uncalibrated link
listed is excluded, with its sign, and the total is incomplete in that direction, not zero.

| Path (first value) | Calculated on the path (calibrated causal) | Accounting (fixed weights) | Excluded: uncalibrated, with sign | Inputs that prevent a size (status) | Forecast (+1 sd): routes to the endpoint fully quantified, and what supplies the size | Trace: routes reaching an endpoint, stops |
|---|---|---|---|---|---|---|
| `tm.path.asset_marks_liabilities` (`jgbs.yield_30y`) | none | 0 | `tm-c-bondmark-equity` (+), `tm-c-bondmark-esr` (+), `tm-c-jgb-bondmark` (-), `tm-c-jgb-liability` (-), `tm-c-liability-esr` (-) | ESR sensitivity to interest rates by shock (not disclosed in reviewed sources); bond holdings by accounting classification and duration (not disclosed in reviewed sources); net asset sensitivity to yen rates (found not connected) | 0 of 6 to `esr`; `m21`, `m23` | 6 of 7; `net_assets` |
| `tm.path.capital_payout` (`tokio_marine.international_profit`) | none | 0 | `tm-c-capital-returns` (+), `tm-c-intl-remit` (+), `tm-c-remit-capital` (+) | none named | 0 of 2 to `shareholder_returns`; `m22` | 2 of 2; none |
| `tm.path.catastrophe_reinsurance` (`tokio_marine.japan_nat_cat_losses`) | none | 2 | `tm-c-cat-profit` (-), `tm-c-cat-reins` (+), `tm-c-reins-profit` (-), `tm-c-reins-rates` (+) | natural catastrophe budget versus actual (found connected); reinsurance recoveries and ceded cost by business (not disclosed in reviewed sources) | 0 of 4 to `operating_profit`; nothing | 5 of 5; none |
| `tm.path.claims_inflation_repricing` (`japan_economy.core_cpi`) | none | 2 | `tm-c-cpi-severity` (+), `tm-c-loss-profit` (-), `tm-c-loss-repricing` (+), `tm-c-premium-earned` (+), `tm-c-rate-loss` (-), `tm-c-rate-premium` (+), `tm-c-rate-retention` (-), `tm-c-retention-premium` (+), `tm-c-severity-loss` (+), `tm-c-severity-reserves` (-) | IFRS insurance revenue by line (not disclosed in reviewed sources); IFRS insurance service result by line (not disclosed in reviewed sources); reserve triangles (not disclosed in reviewed sources); settlement pattern by line (not disclosed in reviewed sources) | 8 of 12 to `operating_profit`; `tm-c-fx-reserves`, `m19`, `m21`, `m22`, `m23`, `s70`, `s55` | 31 of 40; `net_assets`, `share_price` |
| `tm.path.cross_holding_disposal` (`tokio_marine.cross_holding_sales`) | none | 4 | `tm-c-capital-ma` (+), `tm-c-capital-returns` (+), `tm-c-jtd-nii` (+), `tm-c-sale-book` (-), `tm-c-sale-capital` (+), `tm-c-sale-dividends` (-), `tm-c-sale-esr` (+) | IFRS investment income by asset class (not disclosed in reviewed sources) | 0 of 1 to `excess_capital`; nothing | 4 of 5; `net_assets` |
| `tm.path.domestic_yields` (`jgbs.yield_30y`) | none | 5 | `tm-c-jgb30-ife` (-), `tm-c-jgb30-life` (+), `tm-c-jgb30-nmy` (+), `tm-c-nmy-income` (+) | Japan Life investment assets and income yield (found connected); discount-rate locking by cohort (not disclosed in reviewed sources); reinvested share per year (Japan Life) (not disclosed in reviewed sources); reinvested share per year (Japan P&C) (not disclosed in reviewed sources); tenor mix of new purchases (Japan P&C) (not disclosed in reviewed sources) | 1 of 4 to `operating_profit`; `m21`, `m23` | 6 of 7; `net_assets` |
| `tm.path.equity_marks` (`japan_capital_markets.equity_index`) | none | 0 | `tm-c-topix-xholding` (+), `tm-c-xholding-equity` (+), `tm-c-xholding-esr` (+) | none named | 0 of 1 to `esr`; `s70` | 1 of 3; `net_assets`, `share_price` |
| `tm.path.fx_hedge_cost` (`federal_reserve.policy_rate`) | none | 3 | `tm-c-fed-hedge` (+), `tm-c-hedge-nii` (-) | FX hedge notional and hedge ratio (not disclosed in reviewed sources); FX hedging cost, J-GAAP, latest quarter (found connected); IFRS line of the hedge cost (not disclosed in reviewed sources) | 11 of 14 to `operating_profit`; `tm-c-fx-reserves`, `m22`, `m20`, `m19`, `m23`, `s70`, `s55`, `m21`, `s41` | 34 of 42; `net_assets`, `overseas_remittances`, `share_price` |
| `tm.path.growth_execution` (`tokio_marine.excess_capital`) | none | 2 | `tm-c-acquired-intl` (+), `tm-c-capital-ma` (+), `tm-c-ma-earnings` (+), `tm-c-ma-esr` (-) | none named | 0 of 1 to `operating_profit`; nothing | 3 of 3; none |
| `tm.path.international_reinvestment` (`us_treasuries.yield_10y`) | none | 5 | `tm-c-intl-nmy-income` (+), `tm-c-ust-ife` (-), `tm-c-ust-nmy` (+) | floating-rate share (North America) (not disclosed in reviewed sources); reinvested share per year (North America) (not disclosed in reviewed sources) | 6 of 12 to `operating_profit`; `m20`, `m22`, `m21`, `s41`, `m23`, `tm-c-fx-reserves`, `m19`, `s55`, `s70` | 20 of 23; `net_assets`, `share_price` |
| `tm.path.overseas_translation` (`dollar_yen.usd_jpy`) | `m19`, `tm-c-fx-reserves` | 2 | none | basis of the disclosed FX sensitivity (J-GAAP or IFRS adjusted) (found connected); company per-yen FX sensitivity of overseas profit (found connected) | 3 of 3 to `operating_profit`; `tm-c-fx-reserves`, `m19`, `m22`, `m23`, `s70`, `s55` | 6 of 8; `net_assets`, `share_price` |
| `tm.path.policy_growth` (`japan_economy.gdp_growth`) | none | 2 | `tm-c-exposure` (+), `tm-c-exposure-premium` (+), `tm-c-premium-earned` (+) | IFRS insurance revenue by line (not disclosed in reviewed sources); insured exposure by line (not disclosed in reviewed sources) | 8 of 11 to `operating_profit`; `tm-c-fx-reserves`, `m19`, `m21`, `s70`, `m23`, `m22`, `s55` | 29 of 40; `net_assets`, `share_price` |
| `tm.path.reinvestment` (`tokio_marine.jpc_investment_portfolio`) | none | 3 | `tm-c-ani-esr` (+), `tm-c-ani-returns` (+), `tm-c-cash-invest` (+), `tm-c-invest-income` (+), `tm-c-portfolio-cash` (+) | Japan P&C investment assets and income yield (found connected); allocation of new money by asset class, currency and tenor (not disclosed in reviewed sources); annual securities purchases, sales and redemptions (consolidated cash flow) (found connected); cohort sizes of maturing assets (not disclosed in reviewed sources); maturity ladder (not disclosed in reviewed sources); net premium cash flow (Japan P&C) (found not connected); turnover by asset class (not disclosed in reviewed sources); yield of maturing assets (not disclosed in reviewed sources) | 0 of 1 to `operating_profit`; nothing | 1 of 1; none |
| `tm.path.us_liability_reserves` (`tokio_marine.us_liability_severity`) | none | 5 | `tm-c-intl-npw-profit` (+), `tm-c-intl-pyd-profit` (-), `tm-c-intl-rate-npw` (+), `tm-c-intl-rate-profit` (+), `tm-c-tmnf-usliab-profit` (-), `tm-c-usliab-intl` (+), `tm-c-usliab-reprice` (+), `tm-c-usliab-tmnf` (+) | US liability reserve additions (amounts) (found connected) | 0 of 5 to `operating_profit`; nothing | 5 of 5; none |
| `generalization trace: BoJ hike` (`boj.policy_rate`) | - | - | - | see the links it reaches | 10 of 14 to `operating_profit`; `tm-c-fx-reserves`, `m19`, `m21`, `s70`, `m22`, `m23`, `s55` | 27 of 36; `net_assets`, `share_price` |

Read the table this way:

- **Fully sized.** Only `tm.path.overseas_translation` is sized end to end. Its two calibrated links come from the
  disclosed per-yen sensitivity.
- **Sized only by a reduced-form link.** In `tm.path.domestic_yields` and `tm.path.international_reinvestment` the
  structural steps are unsized. Their quantified share comes from the reduced-form links `m21` and `m20`, which
  summarize these paths and are never added to them.
- **Sized only through macro routes.** The quantified share in `tm.path.claims_inflation_repricing`,
  `tm.path.policy_growth` and `tm.path.fx_hedge_cost` comes from the yen and yields (`m19`, `tm-c-fx-reserves`, `m20`,
  `m21`), not from the path's own steps. Those steps contribute no size.
- **Signs only.** The underwriting, reserve, catastrophe, reinvestment, marks, cross-holding, capital and growth paths
  have signs but no size anywhere: 0 quantified routes to their endpoints.

The generalization trace (a BoJ hike, for which no path was written) reaches group adjusted net income with 10 of 14
routes fully quantified, through translation and the reserve counter-effect. It stops at shareholders' equity and the
share price.

## Readable view

Generated by `uv run python scripts/construction/check.py sally_demo --entities tokio_marine` from the loaded model
(the same objects the API serves at `/v1/world-models/sally_demo/entities/tokio_marine/construction`). A `?` marks a step whose size is
unknown (uncalibrated). Levels are left out here; the local copy adds them.

109 links touch its values: 44 calibrated, 65 uncalibrated (represented, size unknown), 36 accounting; 108 carry a transition.

### Business composition

#### reporting segments: adjusted net income by business, company definition (IFRS from FY3/27; excludes gains on business-related equities) (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Tokio Marine international business profit | `tokio_marine.international_profit` |
| Tokio Marine Japan P&C profit | `tokio_marine.japan_pc_profit` |
| Tokio Marine Japan Life adjusted net income | `tokio_marine.japan_life_profit` |
| Tokio Marine solution and other businesses adjusted net income | `tokio_marine.solution_profit` |
| Eliminations: Tokio Marine adjusted net income consolidation adjustment | `tokio_marine.ani_consolidation_adjustment` |
| **Total: Tokio Marine adjusted net income** | `tokio_marine.operating_profit` |

Parts add to the total on this basis only; other views of the same business overlap and are never added to it.
Not the J-GAAP segment-profit view (tm.comp.jgaap_segments): different basis, perimeter and tax treatment.

#### capital: sources and uses of deployable capital (not an additive partition; flows into a stock) (¥bn)

| Part | Value |
|---|---|
| Tokio Marine adjusted net income | `tokio_marine.operating_profit` |
| Tokio Marine business-related equity sales | `tokio_marine.cross_holding_sales` |
| Tokio Marine dividends from overseas subsidiaries | `tokio_marine.overseas_remittances` |
| Tokio Marine shareholder returns | `tokio_marine.shareholder_returns` |
| Tokio Marine acquisition spend | `tokio_marine.acquisition_spend` |
| **Total: Tokio Marine deployable excess capital** | `tokio_marine.excess_capital` |

A non-additive view: its parts overlap.
Earnings capacity, parent cash, available regulatory capital and payout policy are related but distinct.

#### investment assets: international financial-related profit: net investment income less insurance finance expense plus other (IFRS, local currency, pre-tax) ($bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Tokio Marine international net investment income | `tokio_marine.intl_net_investment_income` |
| Tokio Marine international insurance finance expense | `tokio_marine.intl_insurance_finance_expense` |
| Residual: Tokio Marine international other financial items | `tokio_marine.intl_financial_residual` |
| **Total: Tokio Marine international financial-related profit** | `tokio_marine.intl_financial_profit` |

Parts add to the total on this basis only; other views of the same business overlap and are never added to it.

#### regions: international adjusted net income in local currency (USD-equivalent at the plan rate): insurance plus financial-related profit, less tax and other ($bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Tokio Marine international insurance-related profit | `tokio_marine.intl_insurance_profit` |
| Tokio Marine international financial-related profit | `tokio_marine.intl_financial_profit` |
| Residual: Tokio Marine international taxes and adjustments | `tokio_marine.intl_tax_and_adjustments` |
| **Total: Tokio Marine international adjusted net income in local currency** | `tokio_marine.intl_profit_local` |

Parts add to the total on this basis only; other views of the same business overlap and are never added to it.
Translated into the yen value by tm-a-intl-translate at the period-average rate (m19 carries the rate).

#### regions: international business-unit profit by unit, pre-IFRS company basis (yen) (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Tokio Marine Philadelphia business-unit profit | `tokio_marine.intl_phly_profit` |
| Tokio Marine Delphi business-unit profit | `tokio_marine.intl_dfg_profit` |
| Tokio Marine HCC business-unit profit | `tokio_marine.intl_tmhcc_profit` |
| Residual: Tokio Marine other international business-unit profit | `tokio_marine.intl_other_bup` |
| **Total: Tokio Marine international business-unit profit** | `tokio_marine.intl_bup` |

Parts add to the total on this basis only; other views of the same business overlap and are never added to it.
Overseas is not one exposure: the asset-intensive unit is investment-income heavy, the specialty units underwriting heavy. Bridged to the IFRS value by an uncalibrated definitional link.

#### underwriting: Japan P&C adjusted net income: insurance-related plus financial-related profit, less tax and other (IFRS) (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Tokio Marine Japan P&C insurance-related profit | `tokio_marine.jpc_insurance_profit` |
| Tokio Marine Japan P&C financial-related profit | `tokio_marine.jpc_financial_profit` |
| Residual: Tokio Marine Japan P&C taxes and adjustments | `tokio_marine.jpc_tax_and_adjustments` |
| **Total: Tokio Marine Japan P&C profit** | `tokio_marine.japan_pc_profit` |

Parts add to the total on this basis only; other views of the same business overlap and are never added to it.

#### investment assets: Japan P&C financial-related profit: net investment income less insurance finance expense plus other (IFRS, pre-tax) (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Tokio Marine Japan P&C net investment income | `tokio_marine.jpc_net_investment_income` |
| Tokio Marine Japan P&C insurance finance expense | `tokio_marine.jpc_insurance_finance_expense` |
| Residual: Tokio Marine Japan P&C other financial items | `tokio_marine.jpc_financial_residual` |
| **Total: Tokio Marine Japan P&C financial-related profit** | `tokio_marine.jpc_financial_profit` |

Parts add to the total on this basis only; other views of the same business overlap and are never added to it.

#### reporting segments: J-GAAP reportable-segment profit (pre-tax, ordinary-profit based), history through FY3/26 (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Tokio Marine domestic non-life segment profit | `tokio_marine.seg_domestic_nonlife` |
| Tokio Marine domestic life segment profit | `tokio_marine.seg_domestic_life` |
| Tokio Marine international segment profit | `tokio_marine.seg_international` |
| Tokio Marine financial and other segment profit | `tokio_marine.seg_financial_businesses` |
| Eliminations: Tokio Marine segment profit adjustments | `tokio_marine.seg_adjustments` |
| **Total: Tokio Marine total segment profit (J-GAAP)** | `tokio_marine.segment_profit` |

Parts add to the total on this basis only; other views of the same business overlap and are never added to it.
No identity to adjusted net income; never added to tm.comp.ani_by_business.

#### investment assets: J-GAAP net interest and dividends by asset class, main P&C company (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Tokio Marine dividends from domestic equities | `tokio_marine.tmnf_div_domestic_equity` |
| Tokio Marine dividends from foreign equities | `tokio_marine.tmnf_div_foreign_equity` |
| Tokio Marine income from domestic bonds | `tokio_marine.tmnf_inc_domestic_bonds` |
| Tokio Marine income from foreign bonds and securities | `tokio_marine.tmnf_inc_foreign_securities` |
| Residual: Tokio Marine other interest and dividends | `tokio_marine.tmnf_inc_residual` |
| **Total: Tokio Marine Japan P&C net interest and dividends** | `tokio_marine.tmnf_interest_dividends` |

Parts add to the total on this basis only; other views of the same business overlap and are never added to it.
Income by asset class only: balances by class, maturity ladder, currency and hedge notional are not in the sources read, so none is represented.

#### underwriting: J-GAAP net premiums written by line, main P&C company (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Tokio Marine Japan fire premiums | `tokio_marine.tmnf_npw_fire` |
| Tokio Marine Japan voluntary auto premiums | `tokio_marine.tmnf_npw_auto` |
| Tokio Marine Japan marine, personal accident and specialty premiums | `tokio_marine.tmnf_npw_marine_pa_specialty` |
| Residual: Tokio Marine Japan compulsory auto liability premiums | `tokio_marine.tmnf_npw_cali` |
| **Total: Tokio Marine Japan P&C net premiums written** | `tokio_marine.tmnf_npw` |

Parts add to the total on this basis only; other views of the same business overlap and are never added to it.
An activity measure, not profit; compulsory auto liability is a no-profit, no-loss line.

### Operating and financial paths

#### Tokio Marine asset marks and liability valuation

**Trigger:** super-long JGB yields move. **Endpoint:** Tokio Marine economic solvency ratio.

JGB 30Y yield → [assets] Tokio Marine unrealized gains on bonds? → [liabilities] Tokio Marine insurance liabilities at market value? → [equity] Tokio Marine shareholders' equity? → [solvency] Tokio Marine economic solvency ratio? → Tokio Marine economic solvency ratio?  (? marks a step whose size is unknown)

Asset marks and liability valuation are parallel routes to equity and solvency; neither is subtracted from recurring income.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [assets] `tm-c-jgb-bondmark` | Higher yields lower the market value of bonds measured at fair value through OCI; amortized-cost holdings are not marked; recurring income is unaffected (market) | bonds classified at fair value through OCI; duration of those holdings; observable: unrealized gains on bonds in equity | onset immediate; build none; persists until yields reverse or bonds mature; recognized period end | documented / documented / unknown / documented | classification at amortized cost; short duration | unrealized gains on bonds | unknown |
| 2 [liabilities] `tm-c-jgb-liability` | Higher discount rates lower the economic value of long-dated insurance liabilities (a parallel route to the asset mark; matching does not imply full offset) (economic solvency measurement) | liabilities valued at market-consistent rates (solvency basis); J-GAAP reserves are not marked; observable: ESR sensitivity to interest rates (disclosed by shock, not mappable from the source read) | onset immediate; build none; persists until rates reverse; recognized solvency reporting | documented / documented / unknown / documented | duration mismatch; ultimate forward rate extrapolation | insurance liabilities at market value | unknown |
| 3 [equity] `tm-c-bondmark-equity` | Unrealized gains and losses on fair-value bonds move shareholders' equity through OCI, not adjusted net income (group accounts) | fair-value-through-OCI classification; an IFRS 17 OCI option on liabilities may offset part; observable: OCI on debt instruments | onset period end; build none; persists until reversal; recognized quarterly balance sheet | documented / documented / unknown / documented | liability OCI offset | shareholders' equity | unknown |
| 4 [solvency] `tm-c-bondmark-esr` | The asset mark moves economic capital; the liability mark moves it the other way (parallel) (economic solvency measurement) | both sides at market on the solvency basis; observable: ESR and its rate sensitivity | onset immediate; build none; persists until reversal; recognized solvency reporting | documented / inferred / unknown / documented | duration matching | economic solvency ratio | unknown |
| 5 `tm-c-liability-esr` | A higher economic value of liabilities lowers economic capital and the solvency ratio (economic solvency measurement) | observable: ESR and its rate sensitivity | onset immediate; build none; persists until reversal; recognized solvency reporting | documented / documented / unknown / documented | asset duration matching the liabilities | economic solvency ratio | unknown |

Unresolved inputs: ESR sensitivity to interest rates by shock (not disclosed in reviewed sources); bond holdings by accounting classification and duration (not disclosed in reviewed sources); net asset sensitivity to yen rates (found not connected).

#### Tokio Marine capital and payout

**Trigger:** overseas subsidiaries earn and can remit. **Endpoint:** Tokio Marine shareholder returns.

Tokio Marine international business profit → Tokio Marine dividends from overseas subsidiaries? → Tokio Marine deployable excess capital? → Tokio Marine shareholder returns?  (? marks a step whose size is unknown)

Earnings capacity, parent cash, available capital and board payout policy are distinct; a profit move does not by itself decide a dividend.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `tm-c-intl-remit` | Overseas profit becomes parent cash only when subsidiaries remit dividends, subject to local capital rules; remittances do not change group profit (overseas subsidiaries' boards and regulators) | local regulatory capital surplus; no trapped cash; observable: dividends received from subsidiaries | onset annual dividend cycle; build one year; persists per year; recognized parent accounts | documented / inferred / unknown / unknown | trapped cash; local capital stress | dividends from overseas subsidiaries | unknown |
| 2 `tm-c-remit-capital` | Remitted cash adds to capital available at the parent (group capital management) | observable: parent liquidity | onset on receipt; build none; persists until used; recognized parent accounts | inferred / inferred / unknown / unknown | parent obligations | deployable excess capital | unknown |
| 3 `tm-c-capital-returns` | Capital beyond needs can fund buybacks under the board's capital policy; no automatic dividend conclusion follows (board) | solvency above target; parent cash available; no better use; observable: announced buybacks | onset next results or capital announcement; build over the year; persists per decision; recognized equity | documented / inferred / unknown / unknown | acquisitions take priority; capital stress | shareholder returns | unknown |

#### Tokio Marine catastrophes and reinsurance

**Trigger:** a heavy domestic catastrophe season. **Endpoint:** Tokio Marine adjusted net income.

Tokio Marine Japan natural catastrophe losses → [losses] Tokio Marine Japan P&C insurance-related profit? → [reinsurance] Tokio Marine reinsurance cost? → [ceded] Tokio Marine Japan P&C insurance-related profit? → [pass_through] Tokio Marine Japan renewal rate revision? → Tokio Marine Japan P&C profit → Tokio Marine adjusted net income  (? marks a step whose size is unknown)

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [losses] `tm-c-cat-profit` | Domestic catastrophe losses net of reinsurance recoveries lower insurance profit; the variance against the annual catastrophe budget is what moves results versus plan (Japan P&C claims) | losses below the reinsurance retention are borne net; catastrophe-reserve movements apply only on J-GAAP; observable: net incurred natural catastrophe losses versus budget | onset event quarter; build 1-2 quarters of development; persists one-off per event; recognized incurred in the event quarter | documented / documented / unknown / documented | reinsurance recoveries above the retention; catastrophe-reserve release on J-GAAP | Japan P&C insurance-related profit | unknown |
| 2 [reinsurance] `tm-c-cat-reins` | Heavy catastrophe years raise ceded reinsurance prices at the next renewal (reinsurers) | industry-wide losses and reinsurer capital constraints, not one company's losses alone; observable: renewal rate-on-line for catastrophe programmes | onset next reinsurance renewal (often April for Japan); build one renewal; persists until capital returns; recognized ceded premium over the cover period | inferred / inferred / unknown / unknown | abundant reinsurance capital; changed retention | reinsurance cost | unknown |
| 3 [ceded] `tm-c-reins-profit` | Higher reinsurance prices raise ceded premium, lowering net insurance profit unless passed into rates (Japan P&C reinsurance buyers) | programme size unchanged; observable: ceded premium; reinsurance programme terms | onset renewal date; build over the cover period; persists one year per renewal; recognized ceded premium earned over the cover | inferred / inferred / unknown / unknown | higher retention instead of higher cost; strategic reinsurance partnerships | Japan P&C insurance-related profit | unknown |
| 4 [pass_through] `tm-c-reins-rates` | Reinsurance cost increases are a cost of capacity that pricing reviews pass into fire and property rates (Japan P&C pricing) | pricing discretion and competitor behavior allow pass-through; observable: fire rate revisions | onset 1-2 years; build one renewal cycle; persists until the next review; recognized earned over the term | inferred / inferred / unknown / unknown | competitors hold prices | renewal rate change | unknown |
| 5 `tm-a-jpc-insurance` | Insurance-related profit (insurance revenue less claims, expenses and reinsurance) is a pre-tax part of Japan P&C adjusted net income | same scope, currency and IFRS basis; taxes sit in the residual | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Japan P&C adjusted net income | +0.89 sd/sd (accounting) |
| 6 `m23` | Japan P&C adjusted net income is one part of group adjusted net income (company definition); weight is its scale over the total's | same basis (adjusted net income by business, IFRS), period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | group adjusted net income | +0.28 sd/sd (accounting) |

Unresolved inputs: natural catastrophe budget versus actual (found connected); reinsurance recoveries and ceded cost by business (not disclosed in reviewed sources).

#### Tokio Marine claims inflation and repricing

**Trigger:** repair parts, construction and service costs rise. **Endpoint:** Tokio Marine adjusted net income.

Japan core CPI → Japan P&C claim severity? → [losses] Tokio Marine Japan loss ratio? → [reserves] Tokio Marine Japan P&C insurance-related profit? → Tokio Marine Japan renewal rate revision? → [retention] Tokio Marine Japan policy retention? → [premium] Tokio Marine Japan P&C net premiums written? → [margin] Tokio Marine Japan loss ratio? → Tokio Marine Japan P&C net premiums written? → Tokio Marine Japan P&C insurance-related profit? → Tokio Marine Japan P&C insurance-related profit? → Tokio Marine Japan P&C profit → Tokio Marine adjusted net income  (? marks a step whose size is unknown)

Claims costs hit losses and open-claim reserves first; underwriting review reprices with a lag, retention pushes back, and the new rates earn through over a year.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `tm-c-cpi-severity` | Higher prices for repair parts, construction materials and services raise the average cost per claim (repairers, contractors, claimants) | claims inflation follows the relevant cost baskets (parts, labor, construction), not headline CPI one for one; observable: average claim cost by line; repair-cost and construction-cost indices | onset 1-2 quarters; build 1-2 years; persists level shift; recognized as claims are incurred and reserved | inferred / inferred / unknown / unknown | parts or labor deflation; claims-handling efficiencies | claim severity | unknown |
| 2 [losses] `tm-c-severity-loss` | Higher cost per claim at unchanged premiums raises the loss ratio before rates catch up (Japan P&C) | premiums not yet repriced; frequency unchanged; observable: earned/incurred loss ratio by line | onset 1-2 quarters; build until repriced; persists until rates catch up; recognized quarterly results | documented / inferred / unknown / inferred | falling claim frequency; rate increases already earning through | loss ratio | unknown |
| 3 [reserves] `tm-c-severity-reserves` | Open claims are re-estimated at higher costs, a reserve charge that hits insurance profit before any repricing (Japan P&C reserving actuaries) | open claims with long settlement (bodily injury, property) exist; reserves were set at older cost levels; observable: prior-year reserve development; provision for outstanding claims | onset next reserve review; build 1-3 years (settlement pattern); persists one-off per review; recognized quarterly reserve reviews | inferred / inferred / unknown / unknown | reserve margins that absorb the change | Japan P&C insurance-related profit | unknown |
| 4 `tm-c-loss-repricing` | Underwriting review responds to a deteriorating loss ratio with rate revisions, coverage changes and reunderwriting (e.g. fire policies) (Japan P&C pricing and underwriting management) | pricing discretion: rate filings or reference loss-cost revisions for auto; competitors move too; observable: announced rate revisions; renewal rate change by line | onset 1-2 years (filing cycle); build one renewal cycle; persists until the next review; recognized earned over the following year | broker / broker / unknown / unknown | competitors hold prices; regulatory limits on auto rates | renewal rate change | unknown |
| 5 [retention] `tm-c-rate-retention` | Customers facing higher renewal prices shop around or reduce cover (counter-path to repricing) (policyholders and agents) | competitors offer lower prices; switching is easy; observable: renewal retention by line; policy counts | onset at renewal; build one renewal cycle; persists while the gap persists; recognized written premium at renewal | inferred / inferred / unknown / unknown | industry-wide rate increases; sticky agency relationships | policy retention | unknown |
| 6 [premium] `tm-c-rate-premium` | Higher renewal rates raise premium per retained policy (Japan P&C) | policies renew at the new rate; observable: premium per policy; rate change by line | onset at renewal; build one renewal cycle; persists until repriced; recognized written at renewal, earned over the term | documented / inferred / unknown / inferred | lost volume (retention) offsets the price | premiums written | unknown |
| 7 [margin] `tm-c-rate-loss` | Higher earned premium per risk lowers the loss ratio once the new rates earn through (Japan P&C) | claim costs do not rise as fast as rates; retained risks are not worse; observable: loss ratio ex catastrophes by line | onset 1-2 quarters after renewal; build about a year; persists until costs rise again; recognized earned pro rata | broker / broker / unknown / unknown | adverse selection among retained policies; continuing severity inflation | loss ratio | unknown |
| 8 `tm-c-retention-premium` | Higher retention keeps more premium on the books at renewal (Japan P&C agents) | observable: renewal retention; policy counts | onset at renewal; build one cycle; persists while retained; recognized written at renewal | inferred / inferred / unknown / unknown | retention bought with price cuts | premiums written | unknown |
| 9 `tm-c-loss-profit` | A higher loss ratio lowers insurance-related profit; pricing and claims arrive at different times (Japan P&C) | a combined-ratio identity holds only with matching numerator, denominator, gross/net basis and period; the J-GAAP ratio is an operating state here, not the IFRS identity; observable: loss ratio and insurance-related profit on the same period | onset same quarter; build none; persists while the ratio holds; recognized quarterly results | documented / documented / unknown / documented | catastrophe-reserve releases or reserve margins in the same period | Japan P&C insurance-related profit | unknown |
| 10 `tm-c-premium-earned` | Written premium is earned over the policy term and becomes insurance revenue; profit arrives only if the premium covers expected claims and expenses (Japan P&C) | price adequacy: expected loss and expense ratios below 100%; basis bridge J-GAAP written premium to IFRS insurance revenue; observable: combined ratio on a matching earned/incurred basis | onset 1-2 quarters; build over the policy term; persists while priced adequately; recognized earned pro rata | documented / inferred / unknown / inferred | inadequate pricing; claims arriving faster than premiums are repriced | Japan P&C insurance-related profit | unknown |
| 11 `tm-a-jpc-insurance` | Insurance-related profit (insurance revenue less claims, expenses and reinsurance) is a pre-tax part of Japan P&C adjusted net income | same scope, currency and IFRS basis; taxes sit in the residual | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Japan P&C adjusted net income | +0.89 sd/sd (accounting) |
| 12 `m23` | Japan P&C adjusted net income is one part of group adjusted net income (company definition); weight is its scale over the total's | same basis (adjusted net income by business, IFRS), period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | group adjusted net income | +0.28 sd/sd (accounting) |

Unresolved inputs: IFRS insurance revenue by line (not disclosed in reviewed sources); IFRS insurance service result by line (not disclosed in reviewed sources); reserve triangles (not disclosed in reviewed sources); settlement pattern by line (not disclosed in reviewed sources).

#### Tokio Marine cross-holding disposal

**Trigger:** management sells business-related equities under the reduction programme. **Endpoint:** Tokio Marine deployable excess capital.

Tokio Marine business-related equity sales → [income] Tokio Marine dividends from domestic equities? → [book] Tokio Marine business-related equities? → [risk] Tokio Marine economic solvency ratio? → [cash] Tokio Marine deployable excess capital? → Tokio Marine Japan P&C net interest and dividends → Tokio Marine Japan P&C net investment income? → Tokio Marine Japan P&C financial-related profit → Tokio Marine Japan P&C profit → Tokio Marine adjusted net income → [returns] Tokio Marine shareholder returns? → [redeploy] Tokio Marine acquisition spend?  (? marks a step whose size is unknown)

Proceeds and realized gains are capital, not recurring income: the only route into adjusted net income is the forgone dividend (negative).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [income] `tm-c-sale-dividends` | Selling business-related equities gives up their future dividends, a recurring income loss (the realized gain itself is not recurring income) (Japan P&C (sale decision under the reduction programme)) | proceeds are not reinvested at an equal running yield; observable: dividend income from domestic stocks | onset next dividend dates; build as sales proceed; persists permanent; recognized dividend income | documented / inferred / unknown / inferred | proceeds reinvested at a higher yield | dividends from domestic equities | unknown |
| 2 [book] `tm-c-sale-book` | Sales reduce the business-related equity book toward the stated zero target (Japan P&C) | observable: market value of business-related equities | onset on sale; build over the programme; persists permanent; recognized period end | documented / documented / unknown / documented | counterparties resist sales | business-related equities | unknown |
| 3 [risk] `tm-c-sale-esr` | Selling equities and holding the proceeds in lower-risk assets lowers required capital more than it lowers economic capital (group capital management) | proceeds held in lower-risk assets or returned under the capital policy; observable: ESR after sales | onset on sale; build over the programme; persists permanent; recognized solvency reporting | broker / inferred / unknown / unknown | proceeds redeployed into riskier assets or acquisitions | economic solvency ratio | unknown |
| 4 [cash] `tm-c-sale-capital` | After-tax proceeds and released risk capital add to capital that can be redeployed or returned; this is capital, not earnings (group capital management) | tax on realized gains paid; solvency above target range; observable: capital policy disclosures | onset on sale; build over the programme; persists until deployed; recognized capital reporting | broker / broker / unknown / unknown | capital stress elsewhere absorbs it | deployable excess capital | unknown |
| 5 `tm-a-inc-domeq` | Dividends from domestic equities (mostly business-related holdings) are one asset class of interest and dividends | unknown | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Japan P&C interest and dividends | +0.26 sd/sd (accounting) |
| 6 `tm-c-jtd-nii` | The P&C company's J-GAAP interest and dividends, by asset class, is the detail behind Japan P&C IFRS net investment income; not an identity (different basis and perimeter) (Japan P&C) | dividends from overseas subsidiaries in the J-GAAP figure are eliminated in group profit; IFRS measurement differs; observable: both figures for the same period | onset same period; build none; persists identity-like; recognized quarterly | documented / inferred / unknown / documented | subsidiary dividend swings that do not reach group profit | Japan P&C net investment income | unknown |
| 7 `tm-a-jpc-nii` | Gross investment income is the asset side of financial-related profit | same scope and IFRS basis; do not add it again to a profit measure that already includes it | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Japan P&C financial-related profit | +0.72 sd/sd (accounting) |
| 8 `tm-a-jpc-financial` | Financial-related profit (investment result after the liability unwind) is a pre-tax part of Japan P&C adjusted net income; investment underwriting deterioration can outweigh an investment improvement in the same total | same scope, currency and IFRS basis | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Japan P&C adjusted net income | +0.67 sd/sd (accounting) |
| 9 `m23` | Japan P&C adjusted net income is one part of group adjusted net income (company definition); weight is its scale over the total's | same basis (adjusted net income by business, IFRS), period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | group adjusted net income | +0.28 sd/sd (accounting) |
| 10 [returns] `tm-c-capital-returns` | Capital beyond needs can fund buybacks under the board's capital policy; no automatic dividend conclusion follows (board) | solvency above target; parent cash available; no better use; observable: announced buybacks | onset next results or capital announcement; build over the year; persists per decision; recognized equity | documented / inferred / unknown / unknown | acquisitions take priority; capital stress | shareholder returns | unknown |
| 11 [redeploy] `tm-c-capital-ma` | Excess capital funds acquisitions when a target fits risk appetite and price discipline (group management (M&A)) | an opportunity at an acceptable price within management's stated M&A discipline; observable: announced deals | onset deal announcement; build closing (months); persists per deal; recognized at closing | broker / broker / unknown / unknown | no fitting target; price too high | acquisition spend | unknown |

Unresolved inputs: IFRS investment income by asset class (not disclosed in reviewed sources).

#### Tokio Marine domestic yields to reinvestment income

**Trigger:** super-long JGB yields rise. **Endpoint:** Tokio Marine adjusted net income.

JGB 30Y yield → [assets] Tokio Marine Japan P&C new-money yield? → [liabilities] Tokio Marine Japan P&C insurance finance expense? → [life] Tokio Marine Japan Life adjusted net income? → Tokio Marine Japan P&C net investment income? → Tokio Marine Japan P&C financial-related profit → Tokio Marine Japan P&C financial-related profit → Tokio Marine Japan P&C profit → Tokio Marine adjusted net income → Tokio Marine adjusted net income  (? marks a step whose size is unknown)

A JGB move reaches only the new money invested at that tenor, while the liability unwind absorbs part; Japan Life is the long-duration book. m21 is the reduced-form summary of this path and is never added to it.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [assets] `tm-c-jgb30-nmy` | Super-long JGB yields set the yield only on new money invested at super-long tenors; they do not apply to all domestic assets (Japan P&C asset management) | some new money is invested at super-long tenors; observable: tenor mix of purchases (not disclosed) | onset at purchase; build as cash reinvests; persists to maturity; recognized accrual | inferred / inferred / unknown / unknown | no super-long purchases; allocation to other assets | new-money yield | unknown |
| 2 [liabilities] `tm-c-jgb30-ife` | Higher discount rates on new liability cohorts raise the later unwind of discount, absorbing part of the asset uplift (insurance finance expense is negative, so the sign is -) (Japan P&C (IFRS 17 measurement)) | liability discount rates follow yields by cohort (locked-in or current; not disclosed); observable: insurance finance expense trend | onset new cohorts; build years; persists over settlement; recognized quarterly | documented / inferred / unknown / unknown | short-tailed liabilities with little discounting | Japan P&C insurance finance expense | unknown |
| 3 [life] `tm-c-jgb30-life` | Japan Life invests long-duration liabilities in super-long JGBs; new money at higher yields widens the spread over guaranteed rates, slowly (Japan Life asset-liability management) | new money and maturities reinvest at super-long tenors; crediting rates fixed; observable: life income yield; reinvestment share (not disclosed) | onset 1-2 quarters; build many years (low turnover); persists to maturity; recognized accrual | inferred / inferred / unknown / unknown | surrenders; liability unwind at current rates | Japan Life adjusted net income | unknown |
| 4 `tm-c-nmy-income` | A higher new-money yield raises income only on the cash that reinvests, not on the whole book (Japan P&C asset management) | reinvestable cash exists (see the reinvestment path); yield above that of maturing assets; observable: income yield trend; investment-income bridge | onset 1-2 quarters; build years (turnover); persists to maturity; recognized accrual | inferred / inferred / unknown / unknown | low turnover; hedge costs; credit losses | Japan P&C net investment income | unknown |
| 5 `tm-a-jpc-nii` | Gross investment income is the asset side of financial-related profit | same scope and IFRS basis; do not add it again to a profit measure that already includes it | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Japan P&C financial-related profit | +0.72 sd/sd (accounting) |
| 6 `tm-a-jpc-ife` | Insurance finance expense (the unwind of discount on liabilities, negative) is the contract-specific liability side of financial-related profit | IFRS 17 discounting of the liability for incurred claims; locked-in or current rate by cohort (not disclosed) | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Japan P&C financial-related profit | +0.33 sd/sd (accounting) |
| 7 `tm-a-jpc-financial` | Financial-related profit (investment result after the liability unwind) is a pre-tax part of Japan P&C adjusted net income; investment underwriting deterioration can outweigh an investment improvement in the same total | same scope, currency and IFRS basis | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Japan P&C adjusted net income | +0.67 sd/sd (accounting) |
| 8 `m23` | Japan P&C adjusted net income is one part of group adjusted net income (company definition); weight is its scale over the total's | same basis (adjusted net income by business, IFRS), period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | group adjusted net income | +0.28 sd/sd (accounting) |
| 9 `tm-a-ani-life` | Japan Life adjusted net income is one part of group adjusted net income (company definition) | same basis (ANI, IFRS), same fiscal period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | group adjusted net income | +0.35 sd/sd (accounting) |

Unresolved inputs: Japan Life investment assets and income yield (found connected); discount-rate locking by cohort (not disclosed in reviewed sources); reinvested share per year (Japan Life) (not disclosed in reviewed sources); reinvested share per year (Japan P&C) (not disclosed in reviewed sources); tenor mix of new purchases (Japan P&C) (not disclosed in reviewed sources).

#### Tokio Marine equity marks on business-related holdings

**Trigger:** Japanese equities move. **Endpoint:** Tokio Marine economic solvency ratio.

Japan equity index (TOPIX) → Tokio Marine business-related equities? → [equity] Tokio Marine shareholders' equity? → [solvency] Tokio Marine economic solvency ratio?  (? marks a step whose size is unknown)

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `tm-c-topix-xholding` | Business-related equities are marked at market; a rising index raises their value (market) | holdings track the broad index (concentrated holdings may not); observable: market value of business-related equities | onset immediate; build none; persists until sold; recognized period end | documented / documented / unknown / documented | sales shrink the book | business-related equities | unknown |
| 2 [equity] `tm-c-xholding-equity` | Market moves on equities at fair value through OCI change shareholders' equity, never adjusted net income (group accounts) | FVOCI designation under IFRS; observable: OCI on equity instruments | onset period end; build none; persists until reversal; recognized quarterly balance sheet | documented / documented / unknown / documented | deferred tax absorbs part | shareholders' equity | unknown |
| 3 [solvency] `tm-c-xholding-esr` | A higher equity book raises economic capital (and equity risk, less than one for one) (economic solvency measurement) | observable: ESR equity sensitivity | onset immediate; build none; persists until sold; recognized solvency reporting | documented / inferred / unknown / documented | equity risk charge rises with the book | economic solvency ratio | unknown |

#### Tokio Marine FX hedge cost

**Trigger:** the US-Japan short-rate gap widens. **Endpoint:** Tokio Marine adjusted net income.

Fed funds rate (midpoint) → Tokio Marine FX hedge cost on foreign bonds? → Tokio Marine Japan P&C net investment income? → Tokio Marine Japan P&C financial-related profit → Tokio Marine Japan P&C profit → Tokio Marine adjusted net income  (? marks a step whose size is unknown)

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `tm-c-fed-hedge` | Hedging USD assets into yen costs roughly the US-Japan short-rate differential; a higher Fed rate widens it (FX forward market) | foreign bonds are held FX-hedged with rolling short-dated forwards; observable: 3-month USD-JPY forward points; hedge notional (not disclosed) | onset next roll; build within months; persists while the gap holds; recognized each roll | documented / inferred / unknown / inferred | unhedged holdings; longer-dated hedges | FX hedge cost | unknown |
| 2 `tm-c-hedge-nii` | Hedge cost consumes the yield benefit of hedged foreign bonds; net of hedging, a higher foreign yield may add little (Japan P&C asset management) | a hedged foreign bond notional exists (not disclosed); the IFRS line where hedge cost is recognized is not stated; observable: hedge cost disclosed in results (J-GAAP context only) | onset next roll; build within a year; persists while hedged; recognized each roll | documented / documented / unknown / inferred | reducing the hedge ratio (adds FX risk) | Japan P&C net investment income | unknown |
| 3 `tm-a-jpc-nii` | Gross investment income is the asset side of financial-related profit | same scope and IFRS basis; do not add it again to a profit measure that already includes it | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Japan P&C financial-related profit | +0.72 sd/sd (accounting) |
| 4 `tm-a-jpc-financial` | Financial-related profit (investment result after the liability unwind) is a pre-tax part of Japan P&C adjusted net income; investment underwriting deterioration can outweigh an investment improvement in the same total | same scope, currency and IFRS basis | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Japan P&C adjusted net income | +0.67 sd/sd (accounting) |
| 5 `m23` | Japan P&C adjusted net income is one part of group adjusted net income (company definition); weight is its scale over the total's | same basis (adjusted net income by business, IFRS), period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | group adjusted net income | +0.28 sd/sd (accounting) |

Unresolved inputs: FX hedge notional and hedge ratio (not disclosed in reviewed sources); FX hedging cost, J-GAAP, latest quarter (found connected); IFRS line of the hedge cost (not disclosed in reviewed sources).

#### Tokio Marine growth execution

**Trigger:** an acquisition opportunity within risk appetite. **Endpoint:** Tokio Marine adjusted net income.

Tokio Marine deployable excess capital → Tokio Marine acquisition spend? → [earnings] Tokio Marine acquired-business earnings? → [capital] Tokio Marine economic solvency ratio? → Tokio Marine international adjusted net income in local currency? → Tokio Marine international business profit → Tokio Marine adjusted net income  (? marks a step whose size is unknown)

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `tm-c-capital-ma` | Excess capital funds acquisitions when a target fits risk appetite and price discipline (group management (M&A)) | an opportunity at an acceptable price within management's stated M&A discipline; observable: announced deals | onset deal announcement; build closing (months); persists per deal; recognized at closing | broker / broker / unknown / unknown | no fitting target; price too high | acquisition spend | unknown |
| 2 [earnings] `tm-c-ma-earnings` | An acquisition adds earnings after financing cost, dilution, reserve adequacy and integration; the purchase price decides the return (group management) | price below value; reserves adequate; integration succeeds; observable: acquired unit profit versus deal case | onset closing; build 1-3 years; persists while owned; recognized consolidated from closing | broker / broker / unknown / unknown | overpaying; reserve deficiencies; integration failure | acquired-business earnings | unknown |
| 3 [capital] `tm-c-ma-esr` | Acquisitions consume economic capital (price above net assets plus the acquired risk) (group capital management) | observable: ESR after the deal | onset closing; build none; persists until earned back; recognized solvency reporting | inferred / inferred / unknown / unknown | funded by new equity or partner capital | economic solvency ratio | unknown |
| 4 `tm-c-acquired-intl` | Acquired overseas earnings join international profit in local currency (inorganic growth, kept apart from organic growth) (group reporting) | consolidated (not equity-accounted); intangible amortization treatment per the ANI definition; observable: growth split organic versus inorganic | onset closing; build none; persists while owned; recognized from closing | inferred / inferred / unknown / unknown | equity-accounted stake (profit share only) | international profit in local currency | unknown |
| 5 `tm-a-intl-translate` | Yen international profit is local-currency profit times the period-average reporting rate; this link carries the local operating change at a constant rate, m19 carries the rate (in log terms the two add) | translation at the period-average rate; local growth and the FX effect are reported separately (growth ex-FX); observable: reported growth versus growth ex-FX | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | a hedge of translated earnings would change the yen outcome (none represented); investor-currency return is not issuer translation | international adjusted net income in yen | +1.00 sd/sd (accounting) |
| 6 `m22` | International adjusted net income is one part of group adjusted net income (company definition); weight is its scale over the total's | same basis (adjusted net income by business, IFRS), period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | group adjusted net income | +0.80 sd/sd (accounting) |

#### Tokio Marine US yields to international investment income

**Trigger:** US Treasury yields rise. **Endpoint:** Tokio Marine adjusted net income.

UST 10Y yield → [assets] Tokio Marine North America new-money yield? → [liabilities] Tokio Marine international insurance finance expense? → Tokio Marine international net investment income? → Tokio Marine international financial-related profit → Tokio Marine international financial-related profit → Tokio Marine international adjusted net income in local currency → Tokio Marine international business profit → Tokio Marine adjusted net income  (? marks a step whose size is unknown)

US yields reach the share of the North America book that reinvests, net of the liability unwind; m20 is the reduced-form summary and is never added to it.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [assets] `tm-c-ust-nmy` | US Treasury yields plus credit spreads set the yield on new USD fixed income bought by the North America units; it does not apply to all international assets (loans, floating-rate and non-US assets differ) (North America asset management) | purchases are fixed-rate USD bonds near that tenor; spreads unchanged; observable: new-money yield disclosures; tenor and credit mix (not disclosed) | onset at purchase; build as the book turns over; persists to maturity; recognized accrual | documented / inferred / unknown / inferred | spread tightening; allocation to loans or floating-rate assets | North America new-money yield | unknown |
| 2 [liabilities] `tm-c-ust-ife` | Higher discount rates on new international liability cohorts raise the later unwind, absorbing much of the asset uplift (international units (IFRS 17 measurement)) | discounted liabilities (benefits and asset-intensive business especially); observable: insurance finance expense trend versus investment income | onset new cohorts; build years; persists over settlement; recognized quarterly | documented / inferred / unknown / unknown | short-tailed liabilities | international insurance finance expense | unknown |
| 3 `tm-c-intl-nmy-income` | Higher new-money yields raise income on the share of the North America book that reinvests each year (North America units) | turnover of the fixed-rate book; floating-rate assets reprice faster; observable: portfolio income yield; expected investment income guidance | onset 1-2 quarters; build years; persists to maturity; recognized accrual | documented / inferred / unknown / inferred | credit losses (e.g. commercial real estate lending); lower turnover | international net investment income | unknown |
| 4 `tm-a-intl-nii` | International net investment income is the asset side of financial-related profit | unknown | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | international financial-related profit | +0.90 sd/sd (accounting) |
| 5 `tm-a-intl-ife` | The unwind of discount on international insurance liabilities (negative) absorbs part of investment income | unknown | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | international financial-related profit | +0.53 sd/sd (accounting) |
| 6 `tm-a-intl-financial` | International financial-related profit is a pre-tax part of international adjusted net income in local currency | same scope and basis, before translation | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | international profit in local currency | +0.62 sd/sd (accounting) |
| 7 `tm-a-intl-translate` | Yen international profit is local-currency profit times the period-average reporting rate; this link carries the local operating change at a constant rate, m19 carries the rate (in log terms the two add) | translation at the period-average rate; local growth and the FX effect are reported separately (growth ex-FX); observable: reported growth versus growth ex-FX | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | a hedge of translated earnings would change the yen outcome (none represented); investor-currency return is not issuer translation | international adjusted net income in yen | +1.00 sd/sd (accounting) |
| 8 `m22` | International adjusted net income is one part of group adjusted net income (company definition); weight is its scale over the total's | same basis (adjusted net income by business, IFRS), period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | group adjusted net income | +0.80 sd/sd (accounting) |

Unresolved inputs: floating-rate share (North America) (not disclosed in reviewed sources); reinvested share per year (North America) (not disclosed in reviewed sources).

#### Tokio Marine overseas translation

**Trigger:** the yen weakens against the dollar. **Endpoint:** Tokio Marine adjusted net income.

USD/JPY → [translation] Tokio Marine international business profit → [reserves] Tokio Marine Japan P&C profit → Tokio Marine adjusted net income → Tokio Marine adjusted net income

Translation raises yen overseas profit while foreign-currency claims reserves in Japan P&C cost part of it back; overseas share is not the FX sensitivity.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [translation] `m19` | Overseas profit earned in local currency translates into more yen when the yen is weaker (period-average rate); the local operating result is carried separately by tm-a-intl-translate (group reporting) | no hedge of translated earnings; the dollar is the main but not the only currency (s55 carries the euro); observable: reported growth versus growth ex-FX; disclosed per-yen sensitivity of overseas profit | onset same quarter (average rate); build through the fiscal year; persists while the rate holds; recognized quarterly results | documented / documented / documented / documented | Japan P&C foreign-currency reserves move the other way (tm-c-fx-reserves); investor-currency return is not issuer translation | international adjusted net income in yen | +0.45 sd/sd |
| 2 [reserves] `tm-c-fx-reserves` | Japan P&C holds claims reserves in foreign currency; a weaker yen raises their yen value at the period-end rate, a charge that offsets part of the translation gain on overseas profit (Japan P&C (reserving)) | foreign-currency outstanding claims reserves exist and are not fully matched by foreign-currency assets in the same line; observable: provision or reversal of foreign-currency outstanding claims reserves in the P&C company's results | onset period end; build none; persists until the rate reverses; recognized quarterly results at the period-end rate | documented / documented / documented / documented | asset-side FX gains in the same company or a change in reserve currency mix; a reversal of the rate reverses it | Japan P&C adjusted net income | -0.69 sd/sd |
| 3 `m22` | International adjusted net income is one part of group adjusted net income (company definition); weight is its scale over the total's | same basis (adjusted net income by business, IFRS), period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | group adjusted net income | +0.80 sd/sd (accounting) |
| 4 `m23` | Japan P&C adjusted net income is one part of group adjusted net income (company definition); weight is its scale over the total's | same basis (adjusted net income by business, IFRS), period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | group adjusted net income | +0.28 sd/sd (accounting) |

Unresolved inputs: basis of the disclosed FX sensitivity (J-GAAP or IFRS adjusted) (found connected); company per-yen FX sensitivity of overseas profit (found connected).

#### Tokio Marine policy growth

**Trigger:** customers' insurable exposures grow (vehicles, property, commercial activity). **Endpoint:** Tokio Marine adjusted net income.

Japan real GDP growth → Tokio Marine Japan insured exposure? → Tokio Marine Japan P&C net premiums written? → Tokio Marine Japan P&C insurance-related profit? → Tokio Marine Japan P&C profit → Tokio Marine adjusted net income  (? marks a step whose size is unknown)

Exposure growth reaches profit only through earned premium at adequate prices; written premium is not earned profit.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `tm-c-exposure` | Domestic activity grows what customers need insured (vehicles, property values, commercial activity and new risks such as cyber and data centres) (customers (households and companies)) | insurable activity grows, not only nominal prices; observable: new vehicle registrations, construction starts, commercial activity indices | onset 1-2 quarters; build 1 year; persists while activity holds; recognized unknown | inferred / inferred / unknown / unknown | a shrinking vehicle fleet or underinsurance; exposure growth without matching price | insured exposure | unknown |
| 2 `tm-c-exposure-premium` | More insured units at the same rate raise new business and renewal premiums, subject to underwriting appetite (Japan P&C underwriters and agents) | underwriting appetite accepts the added risk at adequate prices; observable: premium growth decomposed into exposure, rate and retention | onset at renewal; build one renewal cycle (about a year); persists while held; recognized written when bound, earned over the term | documented / inferred / unknown / inferred | risk selection that declines growth; competitor pricing | premiums written | unknown |
| 3 `tm-c-premium-earned` | Written premium is earned over the policy term and becomes insurance revenue; profit arrives only if the premium covers expected claims and expenses (Japan P&C) | price adequacy: expected loss and expense ratios below 100%; basis bridge J-GAAP written premium to IFRS insurance revenue; observable: combined ratio on a matching earned/incurred basis | onset 1-2 quarters; build over the policy term; persists while priced adequately; recognized earned pro rata | documented / inferred / unknown / inferred | inadequate pricing; claims arriving faster than premiums are repriced | Japan P&C insurance-related profit | unknown |
| 4 `tm-a-jpc-insurance` | Insurance-related profit (insurance revenue less claims, expenses and reinsurance) is a pre-tax part of Japan P&C adjusted net income | same scope, currency and IFRS basis; taxes sit in the residual | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Japan P&C adjusted net income | +0.89 sd/sd (accounting) |
| 5 `m23` | Japan P&C adjusted net income is one part of group adjusted net income (company definition); weight is its scale over the total's | same basis (adjusted net income by business, IFRS), period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | group adjusted net income | +0.28 sd/sd (accounting) |

Unresolved inputs: IFRS insurance revenue by line (not disclosed in reviewed sources); insured exposure by line (not disclosed in reviewed sources).

#### Tokio Marine reinvestment

**Trigger:** existing holdings mature or pay while market yields differ from book yields. **Endpoint:** Tokio Marine adjusted net income.

Tokio Marine Japan P&C investment assets → Tokio Marine Japan P&C cash available to reinvest? → Tokio Marine Japan P&C new investments? → Tokio Marine Japan P&C net investment income? → Tokio Marine Japan P&C financial-related profit → Tokio Marine Japan P&C profit → Tokio Marine adjusted net income → [payout] Tokio Marine shareholder returns? → [capital] Tokio Marine economic solvency ratio?  (? marks a step whose size is unknown)

The six reinvestment transitions: existing assets -> eligible cash -> chosen investments -> earned income -> net investment result -> segment profit -> group earnings and capacity. Sizes are unknown: no maturity ladder, allocation or hedge notional is disclosed, so a new yield is never applied to the whole portfolio.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `tm-c-portfolio-cash` | Maturities, redemptions and coupons on existing holdings, plus net premium cash after claims, are the cash that can reinvest (Japan P&C asset management) | holdings actually mature or pay in the period; claims and liquidity needs are covered first; observable: maturity ladder and forecast net cash flows (not disclosed) | onset actual cash dates; build unknown; persists unknown; recognized not recognized in profit until invested and earned | inferred / inferred / unknown / unknown | lower turnover; cash needed for claims or buybacks reduces the deployable balance | cash available to reinvest | unknown |
| 2 `tm-c-cash-invest` | The mandate, risk and capital budget, and asset allocation decide which assets, currencies and tenors the cash buys (Japan P&C investment committee) | allocation goes to fixed income at current yields rather than to cash, equities or debt reduction; observable: trades, currency and maturity choices (not disclosed) | onset execution dates; build unknown; persists holding period; recognized none until income accrues | inferred / inferred / unknown / unknown | constraints or allocation to other assets change the yield exposure | new investments | unknown |
| 3 `tm-c-invest-income` | New investments accrue income at their actual yield over the holding period: incremental income = cash invested x incremental yield x holding fraction, by cohort (Japan P&C asset management) | the actual yield exceeds that of the maturing assets; credit performance holds; observable: portfolio income yield and the investment-income bridge | onset from purchase date; build accrues over time (cohort by cohort); persists to maturity; recognized accrual each quarter | inferred / inferred / unknown / inferred | defaults, a lower actual yield or delayed investment erode the uplift | Japan P&C net investment income | unknown |
| 4 `tm-a-jpc-nii` | Gross investment income is the asset side of financial-related profit | same scope and IFRS basis; do not add it again to a profit measure that already includes it | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Japan P&C financial-related profit | +0.72 sd/sd (accounting) |
| 5 `tm-a-jpc-financial` | Financial-related profit (investment result after the liability unwind) is a pre-tax part of Japan P&C adjusted net income; investment underwriting deterioration can outweigh an investment improvement in the same total | same scope, currency and IFRS basis | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Japan P&C adjusted net income | +0.67 sd/sd (accounting) |
| 6 `m23` | Japan P&C adjusted net income is one part of group adjusted net income (company definition); weight is its scale over the total's | same basis (adjusted net income by business, IFRS), period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | group adjusted net income | +0.28 sd/sd (accounting) |
| 7 [payout] `tm-c-ani-returns` | Dividends follow a payout policy on adjusted net income; a higher recurring profit supports a higher payout, by board decision (board) | solvency within or above target; payout policy unchanged; observable: dividend per share and payout ratio announcements | onset next fiscal-year decision; build annual; persists progressive dividend policy; recognized on declaration | documented / documented / unknown / documented | capital stress; payout constraints; per-share figures need split normalization | shareholder returns | unknown |
| 8 [capital] `tm-c-ani-esr` | Earnings retained after payout add to economic capital (earnings capacity, distinct from cash and regulatory capital) (group) | observable: ESR roll-forward | onset period end; build none; persists cumulative; recognized solvency reporting | inferred / inferred / unknown / unknown | payout above earnings | economic solvency ratio | unknown |

Unresolved inputs: Japan P&C investment assets and income yield (found connected); allocation of new money by asset class, currency and tenor (not disclosed in reviewed sources); annual securities purchases, sales and redemptions (consolidated cash flow) (found connected); cohort sizes of maturing assets (not disclosed in reviewed sources); maturity ladder (not disclosed in reviewed sources); net premium cash flow (Japan P&C) (found not connected); turnover by asset class (not disclosed in reviewed sources); yield of maturing assets (not disclosed in reviewed sources).

#### Tokio Marine US liability reserves and specialty repricing

**Trigger:** US liability claim costs (legal and social inflation) rise. **Endpoint:** Tokio Marine adjusted net income.

US liability claim severity → [japan_pc] Tokio Marine Japan P&C US liability reserve additions? → [international] Tokio Marine international prior-year reserve development? → [repricing] Tokio Marine international renewal rate revision? → Tokio Marine Japan P&C insurance-related profit? → Tokio Marine international insurance-related profit? → [margin] Tokio Marine international insurance-related profit? → [volume] Tokio Marine international net premiums written (local)? → Tokio Marine international insurance-related profit? → Tokio Marine Japan P&C profit → Tokio Marine international adjusted net income in local currency → Tokio Marine international business profit → Tokio Marine adjusted net income → Tokio Marine adjusted net income  (? marks a step whose size is unknown)

The same severity trend reaches Japan P&C (US cover of Japanese clients) and the international units as reserve charges, and the international books as repricing.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [japan_pc] `tm-c-usliab-tmnf` | Rising US liability claim costs force prior-year reserve additions on US liability cover the Japan P&C company sold to Japanese corporate clients' US operations (Japan P&C reserving) | older accident years remain open; reserves were set below emerging severity; observable: prior-year reserve additions on US liability | onset next reserve review; build several years of development; persists one-off per review; recognized quarterly reserve reviews | broker / broker / unknown / broker | completed strengthening on older accident years and reduced exposure stop further large additions (an attributed research view until checked against company disclosure) | US liability reserve additions | unknown |
| 2 [international] `tm-c-usliab-intl` | The same severity trend raises prior-year development on the US units' liability books (international units' reserving) | liability lines with long tails in the units' books; observable: prior-year development by unit | onset next reserve review; build several years; persists one-off per review; recognized quarterly results | inferred / inferred / unknown / unknown | reserve margins; reinsurance on prior years | international prior-year development | unknown |
| 3 [repricing] `tm-c-usliab-reprice` | Specialty underwriters raise liability rates to cover the higher severity trend (international underwriters and the market) | market-wide repricing; underwriting discipline; observable: renewal rate change on US liability | onset 1-2 quarters; build one renewal cycle; persists while severity persists; recognized earned over the term | inferred / inferred / unknown / unknown | soft market; new capacity | international renewal rate change | unknown |
| 4 `tm-c-tmnf-usliab-profit` | Reserve additions are a charge to insurance-related profit in the period booked (Japan P&C) | observable: prior-year development in results | onset booking quarter; build none; persists one-off; recognized quarterly results | broker / documented / unknown / broker | favorable development elsewhere | Japan P&C insurance-related profit | unknown |
| 5 `tm-c-intl-pyd-profit` | Adverse prior-year development is a charge to international insurance-related profit (international units) | observable: prior-year development disclosed by unit | onset booking quarter; build none; persists one-off; recognized quarterly results | inferred / documented / unknown / inferred | favorable development in other lines | international insurance-related profit | unknown |
| 6 [margin] `tm-c-intl-rate-profit` | Rate increases ahead of loss trend widen the margin as they earn through (international underwriters) | rate change exceeds loss-cost trend; observable: rate change versus loss trend by unit; combined ratio | onset 1-2 quarters after renewal; build about a year; persists until trend catches up; recognized earned pro rata | inferred / inferred / unknown / unknown | loss trend above rate change | international insurance-related profit | unknown |
| 7 [volume] `tm-c-intl-rate-npw` | Rate increases raise written premium at constant exposure (international underwriters) | observable: premium growth ex-FX decomposed into rate and exposure | onset at renewal; build one cycle; persists while held; recognized written at renewal | inferred / inferred / unknown / unknown | lost business | international premiums written | unknown |
| 8 `tm-c-intl-npw-profit` | Specialty and other premium growth earns into insurance profit if priced adequately (international units) | adequate pricing; growth not in lines with deteriorating loss trend; observable: growth ex-FX and combined ratio by unit | onset 1-2 quarters; build over the term; persists while priced adequately; recognized earned pro rata | documented / inferred / unknown / inferred | growth into underpriced risk | international insurance-related profit | unknown |
| 9 `tm-a-jpc-insurance` | Insurance-related profit (insurance revenue less claims, expenses and reinsurance) is a pre-tax part of Japan P&C adjusted net income | same scope, currency and IFRS basis; taxes sit in the residual | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Japan P&C adjusted net income | +0.89 sd/sd (accounting) |
| 10 `tm-a-intl-insurance` | International insurance-related profit is a pre-tax part of international adjusted net income in local currency | same scope and basis, before translation | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | international profit in local currency | +0.88 sd/sd (accounting) |
| 11 `tm-a-intl-translate` | Yen international profit is local-currency profit times the period-average reporting rate; this link carries the local operating change at a constant rate, m19 carries the rate (in log terms the two add) | translation at the period-average rate; local growth and the FX effect are reported separately (growth ex-FX); observable: reported growth versus growth ex-FX | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | a hedge of translated earnings would change the yen outcome (none represented); investor-currency return is not issuer translation | international adjusted net income in yen | +1.00 sd/sd (accounting) |
| 12 `m22` | International adjusted net income is one part of group adjusted net income (company definition); weight is its scale over the total's | same basis (adjusted net income by business, IFRS), period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | group adjusted net income | +0.80 sd/sd (accounting) |
| 13 `m23` | Japan P&C adjusted net income is one part of group adjusted net income (company definition); weight is its scale over the total's | same basis (adjusted net income by business, IFRS), period and yen | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | group adjusted net income | +0.28 sd/sd (accounting) |

Unresolved inputs: US liability reserve additions (amounts) (found connected).

## Validation

`tests/scenario/test_construction_tokio_marine.py` (loads sally_demo once):

- Structure: no `validate_construction` problems for the company; the ten compositions and fourteen paths exist; every
  path step has a transition and every uncalibrated step a sign and an "unknown" magnitude; branches of a shared driver
  start at the same value; the reinvestment path's first six steps are the six transitions in order, with payout and
  capital as parallel branches.
- Financial integrity: every part of an additive view has a fixed-weight accounting link to its total, each view keeps
  a residual or eliminations; the adjusted-net-income weights equal each part's native sd over the total's; the J-GAAP
  segment view shares no part and no link with the adjusted-net-income view; asset and liability marks never reach
  recurring income; cross-holding proceeds reach recurring income only as forgone dividends (negative); no maturity
  ladder value exists.
- Calibration: the only new calibrated causal link (`tm-c-fx-reserves`) comes from a disclosed per-yen sensitivity,
  and the net group FX effect keeps the disclosed sign; m20 and m21 state their scope and an "assumption" magnitude.
- Generalization: a BoJ policy-rate rise, for which no path was written, traced through every link (below).
- Second round: every transition input has a status other than `not_yet_reviewed`, and a not-disclosed input lists
  what was searched; the nine additive views reconcile at the model's medians within 0.5%; a forecast of a move in
  `boj.policy_rate` returns `coverage` whose contributed and excluded links split as the readable view says. When
  the local client folder exists (not on CI), every cited source id resolves in `sources.json`, no material claim
  lacks a located citation in `citations.json`, every citation key names a model object, and the FY3/26 baselines
  reconcile in every view.
- Delivery: compositions in `financial_bridge`, named paths as `business_construction` transmission paths, m22/m23 as
  `accounting_identity` with metric `adjusted_net_income`, uncalibrated links as `represented_uncalibrated` with their
  sign, `schema_gaps` present (all from `/v1/world-models/sally_demo/exports/v4.1.4`); new node ids returned by
  `/v1/world-models/sally_demo/graph`, the construction and trace endpoints.

Sally's expected paths (`tests/scenario/test_sally_expected_paths.py`) still pass: `international_profit`,
`japan_pc_profit` and `operating_profit` keep their ids, m19–m21 keep their sizes, and m22/m23 still carry a positive
effect into `operating_profit`.

**Generalization trace (BoJ hike).** Routes that reach a financial endpoint: m16 → m19 → m22 (translation, calibrated)
into group adjusted net income; m16 → `tm-c-fx-reserves` (the offsetting reserve effect, calibrated) into Japan P&C;
`tm-c-boj-hedge` → `tm-c-hedge-nii` → `tm-a-jpc-nii` (a cheaper hedge, uncalibrated) into Japan P&C financial profit;
m13 → `tm-c-jgb10-nmy` → `tm-c-nmy-income` (new-money yields, uncalibrated); m13 → m14 → `tm-c-jgb30-ife` (the liability
unwind, uncalibrated); m13 → m14 → asset and liability marks (parallel, uncalibrated) into solvency; m16 → m19 →
remittances into excess capital. Where it stops: shareholders' equity (`net_assets`) and the share price, which lead
nowhere further; and every uncalibrated step, where the direction is known but the size is not, so a forecast lists
it as unquantified rather than adding zero.

## Completion report

Outcomes map to the release outcomes: built and verified (**BV**), built but uncalibrated (**BU**), blocked by a named
input (**BL**), not built (**NB**).

| # | Outcome | What is in the model now | What remains |
|---|---|---|---|
| G01 | BV | `operating_profit` names its basis and exports as `adjusted_net_income`; m22/m23 are accounting links with sd-ratio weights; Japan Life, solution and consolidation-adjustment parts added | levels of the new parts are synthetic until the local baselines are imported |
| G02 | BV | `tm.comp.jgaap_segments`, separate basis, no link to the ANI view | — |
| G03 | BL | gap kept visible: no statutory-to-adjusted bridge | company reconciliation of net income to adjusted net income by business |
| G04 | BV (structure) / BU (drivers) | `tm.comp.japan_pc_ani`, `tm.comp.japan_pc_financial`; both reconcile at the priors and the FY3/26 baselines | the company's Japan P&C insurance-related profit (the baseline derives it; the residual is the explicit unexplained difference); IFRS income by asset class (not disclosed) |
| G05 | BV (structure) / BU (drivers) | local-currency composition, accounting translation, business-unit view | IFRS split by international unit; regional profit outside North America |
| G06 | BV | `tm.comp.tmnf_lines` | IFRS insurance revenue by line |
| G07 | BL | income by asset class built; no balances, ladder or hedge notional represented; portfolio sizes and income yields bound (found and connected) | maturity ladder, reinvestable cash flow, tenor and currency mix, hedge notional: searched, not disclosed in the reviewed sources |
| G08 | BU | `tm.path.reinvestment` with the six transitions | sizes blocked by G07 inputs |
| G09 | BU | m20/m21 keep ids and sizes, now with scope, "assumption" magnitude and a no-double-count rule | recalibrate m21 once the domestic yield path can be sized |
| G10 | BU | `tm.path.fx_hedge_cost` | hedge notional and ratio; the IFRS line of the hedge cost |
| G11 | BU | `tm.path.asset_marks_liabilities`, `tm.path.equity_marks` to equity and solvency only | ESR sensitivities mapped by shock; bond classification and duration |
| G12 | BU | `tm.path.claims_inflation_repricing`, `tm.path.policy_growth` | severity, rate filing, retention and exposure data |
| G13 | BU | `tm.path.us_liability_reserves`, `tm.path.catastrophe_reinsurance` | reserve triangles, settlement patterns, reinsurance programme |
| G14 | BV | `tm.path.overseas_translation`; reserve link calibrated from the disclosure; m19 consistent with it | basis (J-GAAP vs IFRS) of the disclosed sensitivity |
| G15 | BV (structure) / BU (sizes) | `tm.path.cross_holding_disposal`; proceeds are capital | dividend yield of the sold holdings |
| G16 | BU | capital values, `tm.path.capital_payout`, non-additive `tm.comp.capital_sources_uses` | parent cash, remittance data |
| G17 | BU | `tm.path.growth_execution` | deal terms and integration evidence |
| G18 | BU | `tm.path.policy_growth` | exposure and quote data |
| G19 | BV | objects present in the v4.1.4 export | — |
| G20 | BV | node ids served by the query, construction and trace endpoints | — |
| G21 | BL | — | the split ratio and effective date, declared as a corporate action ([README](README.md#declare-a-stock-split)) |
| G22 | BV | shared path untouched; company paths exported beside it | — |

### Second round (Oct 18)

| Finding | Outcome | Evidence |
|---|---|---|
| 1 Sources and citations resolve | BV | 13 source ids catalogued locally; 82 links and 48 values cited with location and passage; 0 unresolved ids, 0 uncited material claims |
| 2 Inputs searched before declared missing | BV | 35 inputs: 9 found and connected, 2 found but not connected, 24 not disclosed in the reviewed sources (each with its searched sources and queries), 0 not yet reviewed |
| 3 Numbers satisfy the relationships | BV | 9 of 9 additive views within 0.5% at the medians and at the FY3/26 baselines; one explicit unexplained-difference residual (Japan P&C taxes and other) |
| 4 Calculation coverage | BV | per path and for the generalization trace (above); one path sized end to end, two sized only by their reduced-form summaries, three sized only through macro routes, the rest signed but unsized |
| 5 Method generalizes | BV (method) / BL (sizes) | the full process ran; sizes stay blocked by the inputs the search shows are not disclosed |

**What the method could not express for this company.**

- A derived baseline is not a reported one. The import bundle has no field marking an observe as derived from other
  sources' figures, so the derivation sits in the item's summary and note.
- A sensitivity that nets two parallel links has no place to go. The Japan Life net asset sensitivity is one number
  for the asset and liability marks together. Calibration works one link at a time, so the number cannot be used.
- An input that is found but does not supply a size counts as found and connected, so it stays listed as blocking.
  Examples are a portfolio size, or a group-wide cash flow standing in for a ladder.
- A forecast's quantified share mixes routes. It counts routes through the macro statistical links together with the
  path's own steps, so a high share can hide a path whose own steps are all unsized.

### Conversion round (Oct 18)

The new method forms ([README](README.md#identities-products-ratios-differences)) turn exact steps from signs into
derived weights. Tokio Marine had no total with two driving views, so no view was marked reconciling and no matrix was
declared.

| Form | Object | What it states | Links |
|---|---|---|---|
| Product identity | `tm.id.jpc_nii` | Japan P&C net investment income = 0.01 x investment assets x income yield (a new value, `jpc_income_yield`) | `tm-i-jpc-nii-assets`, `tm-i-jpc-nii-yield` (written, with transitions) |
| Stock-flow | `tm.sf.cross_holdings` | the business-related equity book falls by sales at market value each year | `tm-c-sale-book` (converted) |
| Stock-flow | `tm.sf.parent_capital` | deployable capital at the parent accumulates remittances less shareholder returns and acquisition spend | `tm-c-remit-capital` (converted) and two generated outflow links |
| State (sign flip) | `tm-c-invest-income` | reinvesting raises the book yield while new money yields more than the book, and lowers it below | uncalibrated, sign-only, now conditional |

- **Retargeted onto the yield.** The new-money, hedge-cost and reinvestment links now act on the income yield, not on
  income directly. Income follows through the identity, and the reinvestment, domestic-yields and hedge-cost paths
  gained the identity step.
- **Priors.** The synthetic investment-assets prior became 6,500 and the new-money yield 2.5, so that the identity
  holds at the medians and new money starts above the book yield.

**Links touching Tokio Marine's own values, before and after.** MS&AD's four links into the shared claim-severity
states are not counted.

| Kind | Before | After |
|---|---|---|
| Calibrated causal | 8 | 8 |
| Accounting | 36 | 36 |
| Identity | 0 | 2 |
| Stock-flow | 0 | 4 |
| Uncalibrated (sign-only) | 65 | 63, one of them state-dependent |
| Total | 109 | 113 |

**Checks.**

- **Reconciliation.** The nine additive views still reconcile at the medians and at the FY3/26 baselines. The identity
  reconciles at the medians.
- **The identity at the baselines.** The check is blocked, not flagged: the identity defines its own yield (income over
  assets), and the company's stated income yield has a different definition. Deriving the yield from the two observed
  levels would be circular. No dated stock levels exist, so the roll-forwards have nothing to check.
- **Inputs.** The ESR shock sensitivity is now `disclosed_not_supplied`. A new input, new-money against book yield, is
  found and connected: it fixes the starting side of the sign flip.

**Coverage now.** The forecasts of a +1 sd move in each path's first value were stopped partway to limit machine load,
so the coordinator regenerates the full table centrally. Results for the paths that finished:

- **`tm.path.cross_holding_disposal`.** Its own stock-flow step `tm-c-sale-book` now carries a size into the equity
  book. It is the first own step of a non-translation path to contribute.
- **`tm.path.claims_inflation_repricing`.** Still sized only through the yen and yields (8 of 11 routes).
- **Asset marks, capital payout, catastrophes.** 0 quantified routes to their endpoints.

The identity and stock-flow links carry a size only when a step upstream of them is sized. The reinvestment,
domestic-yields and hedge-cost paths still start with sign-only steps.

**What the conversion could not express.**

- **Products that need undisclosed or unheld values:**
  - premium written needs a price level and an exposure level (the model holds a rate change);
  - the loss ratio needs claims and earned premium held on one basis;
  - the solvency ratio needs economic and required capital, whose shock values are disclosed but not supplied;
  - international investment income needs international assets, and only North America's are held;
  - new investments need the reinvested share.
- **Stocks without balances.** Reserves have no balance, payment pattern or triangle. The portfolio roll is not
  built: with reinvestment unsized, the maturity outflow alone would drain the stock.
- **Thresholds without a level.** The reinsurance retention is not disclosed. The solvency target is a company figure
  kept out of tracked files.
- **No `--disclosure` calibration.** The Japan Life net asset sensitivity is Japan Life only, while the marks are
  group values. It also runs through intermediate values in series, not parallel links into one target. So no
  scenario equation maps it.
- **The sign flip compares with a fixed level.** It compares the new-money yield with the book yield's construction
  level, because a moderator reads one value.

Each candidate left sign-only says why in its `note`.

**What a downstream agent can now trace or calculate.** The group adjusted-net-income total as the sum of five parts on
one basis; the yen international value as local-currency profit times the reporting rate; Japan P&C and international
profit as insurance plus financial-related profit with the liability unwind visible; which assets earn the Japan P&C
company's income; the net group FX effect with its reserve counter-effect (calibrated); and, as signed mechanisms with
conditions, timing, evidence and breakers, how claims inflation, repricing, retention, catastrophes, reinsurance, US
liability reserves, reinvestment, hedging, asset and liability marks, cross-holding sales, acquisitions and remittances
reach the right account.

**What remains unsupported.** Any size for reinvestment, hedging, marks, underwriting and capital links. Ladder,
notional, triangles and ESR shock values were searched for in every supplied source and are not disclosed there; the statutory-to-adjusted bridge; per-share figures
across the split; Japan Life beyond its one yield link. 65 of the 109 links touching Tokio Marine's values are
uncalibrated, 36 are accounting, 8 are calibrated causal (m19, m20, m21, s41, s55, s70, `tm-c-fx-reserves`, and the
kind default from adjusted net income to the share price, which carries no transition).
