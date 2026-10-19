# Toyota Motor: business construction

<!-- toc -->
**Contents**

- [Gap register](#gap-register)
- [Audit before modifying](#audit-before-modifying)
- [Definitions and bases](#definitions-and-bases)
- [Second review round](#second-review-round)
  - [Gap register (second round)](#gap-register-second-round)
  - [What changed, by finding](#what-changed-by-finding)
  - [Inputs by status](#inputs-by-status)
  - [Reconciliation](#reconciliation)
  - [Calculation coverage](#calculation-coverage)
  - [Completion report (second round)](#completion-report-second-round)
- [Conversion round](#conversion-round)
- [Pack round](#pack-round)
  - [Gap register (pack round)](#gap-register-pack-round)
  - [Inputs before and after](#inputs-before-and-after)
  - [Calibrations added](#calibrations-added)
  - [Reconciliation at the new baselines](#reconciliation-at-the-new-baselines)
  - [Coverage now](#coverage-now)
  - [Emily's points: what the pack closes and what stays open](#emilys-points-what-the-pack-closes-and-what-stays-open)
- [Plan round](#plan-round)
  - [Part 1. Before/after audit by canonical id](#part-1-beforeafter-audit-by-canonical-id)
  - [Part 2. Composition and connected paths](#part-2-composition-and-connected-paths)
  - [Part 3. Evidence and calibration](#part-3-evidence-and-calibration)
  - [Part 4. End-to-end checks](#part-4-end-to-end-checks)
- [Batch 2](#batch-2)
  - [A. Before/after record](#a-beforeafter-record)
  - [B. Corrected baselines and provenance](#b-corrected-baselines-and-provenance)
  - [C. Connected scoped finance modules and paths](#c-connected-scoped-finance-modules-and-paths)
  - [D. Seed responses](#d-seed-responses)
  - [E. Residual data](#e-residual-data)
- [Readable view](#readable-view)
  - [Business composition](#business-composition)
  - [Identities](#identities)
  - [Stocks and flows](#stocks-and-flows)
  - [Operating and financial paths](#operating-and-financial-paths)
- [Validation](#validation)
- [Completion report](#completion-report)
- [Repair round (Oct 19)](#repair-round-oct-19)
<!-- /toc -->

The construction lives in `data/worlds/sally_demo/construction/toyota.yaml` (values, links with their transitions,
named paths, compositions) plus light edits to the `toyota` entity and to m29, s42, s43, s44. This page is structure
only: object ids, bases, categories, tests. The client-derived side (workbook rows and cells, formula dependencies,
broker and expert-call readings, dated baselines, the passages behind each citation) stays local under
`data/sally_data/construction/toyota/` (`gap_evidence.md`, `sources.json`, `citations.json`, `baselines.json`,
`bindings.json`, `estimates.json`, `input_search.json`, and the full readable view with levels).

Source ids used in transitions (each resolves locally to a document in `sources.json`, and each material claim to a
located passage in `citations.json`): `ty.wb` sell-side company model workbook (regional, business and
income-statement history, the operating-income change bridge, guidance and monthly unit data; forecasts in it are the
modeler's); `ty.bridge` the workbook's company-sourced operating-income change bridge (transaction and translation FX,
volume and mix, marketing efforts, value chain, cost reduction, expenses); `ty.sm` the client's macro-transmission
model for Toyota (Oct 18: a fact ledger of company-deck figures by document and page, kept apart from its own
inferences); `ty.peer` sector dashboard (peer volumes, share, ASP, zero-emission units); `ty.r1` broker note on the
in-house humanoid robot programme; `ty.r2` broker note on Chinese brands in Southeast Asia and the incumbent's service
network; `ty.xc` expert call on hybrid batteries and dealer service; `ty.robo` robotics dataset workbook; `ty.rates`
the rates and USD/JPY research folder (searched, not cited); `ty.ext` reviewer-cited research not in the local folder
(China JV reorganization, a second robotics note; their content reaches the build through `ty.sm`); `ty.pub` public
business and accounting knowledge (segment and IFRS presentation, how tariffs, subvention and lease residuals work).
Since Oct 18 no claim rests on `ty.pub` alone as documented: such claims were re-labelled or cited to a document.

## Gap register

Written before the model was changed. "Internal" is the loaded sally_demo graph and its YAML; "export" is the v4.1.4
pack the reviewer inspected (036, state version 432). Categories: **MC** missing construction, **CAL** missing
calibration, **MAP** incorrect mapping, **EXP** export omission, **RET** retrieval omission. Outcome codes (filled in
the [completion report](#completion-report)): built and verified / built but uncalibrated / blocked by a named input /
not built.

| # | Gap (missing or incorrect structure) | Present now (internal / export) | Add or correct | Evidence or input needed | Conclusions affected | Test that shows it done | Cat. |
|---|---|---|---|---|---|---|---|
| G01 | Reporting businesses: automotive, financial services, all other, intersegment eliminations | Internal: `toyota.operating_profit`, `toyota.vehicle_sales`, `toyota.share_price` only; no composition. Export: N_TOYOTA_MOTOR with requested fields share price, operating profit, vehicle sales | Composition `ty.comp.reporting_segments` (segment operating income, IFRS) with residual and eliminations; accounting links to `toyota.operating_profit` | Business-segment revenue and operating income (`ty.wb`) | Automotive vs financing contribution; where a shock lands | `test_required_compositions_exist`, `test_additive_views_reconcile_by_accounting_links` | MC |
| G02 | Regional operations: Japan, North America, Europe, Asia, other, eliminations; intersegment flows | Internal: none. Export: none | Composition `ty.comp.regional_operating_income`; regional external revenue `ty.comp.regional_external_revenue`; Japan intersegment revenue kept as its own value (internal supply, not customers) | Regional revenue, intersegment and operating income (`ty.wb`) | Why North America revenue and profit diverge; Japan export contribution | `test_required_compositions_exist`, `test_regional_and_business_views_never_share_a_part` | MC |
| G03 | Customer location versus production location (units and revenue) | Internal: none | Units sold by region `ty.comp.units_by_customer_region` vs units built by region `ty.comp.units_by_production_region`; revenue by customer location `ty.comp.revenue_by_customer_location`; difference identities for Japan export volume and North America import volume | Units, production, revenue by customer location (`ty.wb`) | Tariff exposure, Japan export contribution | `test_customer_and_production_views_are_separate` | MC |
| G04 | Product economics (powertrain) | Internal: none | Retail units by powertrain `ty.comp.retail_units_by_powertrain` (hybrid, plug-in, battery-electric, ICE and other); no product margins | Powertrain retail units (`ty.wb`); product margins are not disclosed | Electrified share vs hybrid profit | `test_no_product_margin_values` | MC / CAL |
| G05 | Financial services: revenue, cost of financing, other expenses; funding cost, contract rate, credit losses, lease residuals, receivables, borrowings | Internal: none | Composition `ty.comp.financial_services` and the operating states its paths need | FS revenue and costs (`ty.wb`); funding cost, credit loss and residual data not in the workbook | Financing support for purchases; funding and credit pressure | `test_required_compositions_exist`, `test_required_paths_exist` | MC / CAL |
| G06 | Affiliates: units retailed by equity-accounted JVs reach equity-method income, not consolidated revenue | Internal: none | `ty.comp.retail_units_bridge` (group retail = consolidated + unconsolidated); `toyota.equity_method_income`; path `ty.path.china_affiliates` | Retail vs consolidated units (`ty.wb`); JV-level profit not in the sources read | Whether China volume reaches revenue or equity income | `test_required_paths_exist` | MC / CAL |
| G07 | s44 vehicle sales → operating profit is misspecified: its learned sign straddles zero; volume alone does not set profit | Internal: s44 causal, calibrated (mu 0.4 at construction; learned to about zero in the exported state). Export: REL_TOYOTA_MOTOR__E69_FIRM_FINANCIALS central -0.04, 90% range across zero | Keep the id; re-route to consolidated volume → automotive revenue, mark uncalibrated with sign + and a transition; profit is reached through revenue, price, mix, cost and the segment identity | none (structural correction) | Every "more units, more profit" conclusion | `test_s44_is_rerouted_and_uncalibrated` | MAP |
| G08 | s42/s43 GDP → global vehicle sales: broad, valid, but global and region-free | Internal: s42, s43 calibrated. Export: E67_ENERGY_TO_ACTIVITY, E67_ENERGY_TO_ACTIVITY__VEHICLE_SALES | Keep ids, sizes and targets (statistical records; Sally's expected paths); add transitions saying they are reduced-form and never added to the regional path | Region-specific evidence (for the path, not these links) | Global volume forecasts | `test_broad_links_keep_their_records_and_gain_transitions` | MAP |
| G09 | Yen: only the aggregate m29; transaction (exports from Japan), translation (overseas profits) and imported-input effects not separate; export labels m29 FX translation although the exposure is mostly transaction | Internal: m29 calibrated, classified `gen:int:fx_translation`. Export: REL_TOYOTA_MOTOR__E70_FX_TRANSLATION; PATH_KOMATSU_YEN_EXPORTERS groups Toyota with Komatsu and TOPIX | Keep m29 as the calibrated aggregate (the company's per-yen sensitivity); add uncalibrated transaction, translation and imported-input branches in `ty.path.yen`, stated never to be added to m29; Komatsu path untouched | Per-yen split of the sensitivity by channel (not disclosed); hedge positions | Yen-to-profit size and where it lands | `test_yen_branches_are_separate_and_never_added_to_the_aggregate` | MC / MAP |
| G10 | Tariffs and sourcing as five transitions: regime → customs cost → management response → customer response → regional economics → group | Internal: none | `ty.path.tariffs_sourcing` with `us_vehicle_tariffs`, import volume, US tariff cost, list price, revenue per vehicle, production response, transfer-price support, feedback to the duty base | Covered origin and content, customs base, duty records, pass-through, elasticities (none in the sources read) | North America and Japan profit under tariffs | `test_tariff_path_has_the_five_transitions` | MC / CAL |
| G11 | Pricing competition (US incentives; Chinese entrants in Southeast Asia) | Internal: none | `ty.path.pricing_competition`, `ty.path.asia_entrants` | Incentive and transaction-price data; regional share | Realized price vs volume | `test_required_paths_exist` | MC / CAL |
| G12 | Regional growth with availability, production and absorption | Internal: s42 only | `ty.path.regional_growth` (US demand → industry volume → North America volume → revenue, production, dealer inventory, imports → North America profit) | Regional demand and inventory data | North America growth vs profit | `test_required_paths_exist` | MC / CAL |
| G13 | Product mix (fuel economics → powertrain choice → units → realized economics) | Internal: none | `ty.path.product_mix`; mix vs volume shown as offsetting branches | Powertrain revenue and margin (not disclosed) | Hybrid demand conclusions | `test_required_paths_exist` | MC / CAL |
| G14 | Financing: funding curve → cost of financing; contract repricing and subvention; arrears; used values → lease outcomes; receivables and borrowings | Internal: none | `ty.path.financing_funding`, `ty.path.financing_credit_residual`; subvention counted once | Funding mix and duration, credit and residual data | Financial-services income; "debt rose, so industrial stress" | `test_required_paths_exist`, `test_financing_debt_is_not_industrial` | MC / CAL |
| G15 | Execution and share (launch pipeline → share → units → regional earnings; capex) | Internal: none | `ty.path.execution_share` | Launch, quality and share data; industrial cash flow split from financial services | Share and cash conversion | `test_required_paths_exist` | MC / CAL |
| G16 | New initiatives (robotics and automation): commitment → deployment → productivity or paid use, after development, depreciation and deployment cost | Internal: none | `ty.path.new_initiatives`; optionality kept separate from established earnings | Deployment schedule, costs, measured savings (not established) | Robotics value claims | `test_required_paths_exist` | MC / CAL |
| G17 | Group bridge below operating profit: equity-method income, other finance income, tax, minorities, net income | Internal: none | `ty.comp.pretax_bridge`, `ty.comp.net_income_bridge`; calibrated tax formula from the documented effective rate; path `ty.path.group_bridge` | Income-statement history (`ty.wb`) | EPS and payout from an operating change | `test_group_bridge_reconciles` | MC |
| G18 | Workbook bindings: which rows drive outputs | Internal: none; the reviewer warns cost rows are display-only | Local `sources.json` records the inspected dependencies: forecast regional operating income = regional total revenue × input margin; business segments are not forecast; cost rows above EBIT are display-only | Formula inspection (`ty.wb`) | Any claim that the workbook supplies a cost sensitivity | local `sources.json` binding entries; no transition cites a display-only row as magnitude evidence | MAP |
| G19 | Transitions, compositions and Toyota paths absent from the inspected export | Export: not represented in the inspected export | Export carries them: transitions in relationship properties, `financial_bridge`, `business_construction` paths | none | Downstream agent context | `test_new_objects_reach_the_export` | EXP |
| G20 | New node ids not retrievable through the service | Internal API: values not yet present | `/v1/world-models/sally_demo/graph` and `…/entities/toyota/construction` serve them | none | Agent retrieval | `test_new_objects_reach_the_api` | RET |
| G21 | The query API reports an uncalibrated link's effect as a number (the unused default) with no calibration field | `api/service.py` `edge()` prints `effect_sd_per_sd` for every link | Report `calibration` and a null effect for uncalibrated links (the construction view and the v4 export already do) | Change in `api/service.py` (not owned by this build) | An agent reading "0.0" as "no effect" | recorded; `test_new_objects_reach_the_api` asserts the construction endpoint marks them | RET |
| G22 | Two views of one total (business segments and regions both sum to operating profit) could both move it | Engine: no constraint between alternative views of a total | Keep both identities; guarantee no calibrated route reaches the total through both views; record the engine limit for observations of parts of both views | Engine support for alternative views (imports already fold one view per item and day: [README](README.md#overlapping-views-at-import)) | Any simulation that calibrates a regional and a business link from one shock | `test_no_calibrated_route_reaches_a_total_through_two_views` | MC |
| G23 | Imported research mapped onto the wrong basis: consolidated volume guidance observed into `toyota.vehicle_sales` (a retail basis); a Southeast Asia share-loss note moved global volume | Internal: Sally's day bundles (not owned by this build) | Re-map to `toyota.consolidated_units` (as guidance, not an observation) and `toyota.asia_market_share` | Bundle owner's change | Volume level and Asia share | recorded; values now exist to map to | MAP |
| G24 | Entity description frames Toyota only as a yen exporter | Internal: `toyota.description` | Describe the composition; keep the yen fact | none | Retrieval context | `test_entity_describes_the_composition` | MAP |

## Audit before modifying

| Requirement | Class | Controlling object | Action |
|---|---|---|---|
| Identity, role, clusters (N_TOYOTA_MOTOR, `toyota`, superentity S8 "Yen exporters") | Already owned | `entities.yaml` `toyota`; `superentity_seeds.yaml` S8 | none |
| m29 yen → operating profit (statistical record; Sally's must channel) | Already owned / Do not touch (size) | `interactions.yaml` m29 | add a transition only |
| s42, s43 GDP → vehicle sales (statistical records) | Already owned / Modify lightly | s42, s43 | add transitions only |
| s44 vehicle sales → operating profit | Modify lightly (re-route, uncalibrated) | s44 | re-route with stated reason (G07) |
| `d-toyota-operating_profit-share_price` (kind default) | Already owned / Do not touch | `taxonomy/objects.yaml` company defaults | none |
| PATH_KOMATSU_YEN_EXPORTERS (parallel exporter responses) | Do not touch | superentity S8 | Toyota's own yen path added beside it |
| Interaction taxonomy class of m29 (`gen:int:fx_translation`) | Modify lightly (not done here: shared taxonomy) | `taxonomy/interactions.yaml` | recorded (G09) |
| Value definitions (`operating_profit`, `vehicle_sales` basis) | Modify lightly | `toyota` entity block | add `features.view` and `features.basis` |
| Composition, paths, financial bridge, bindings | Missing | new `construction/toyota.yaml` | build |
| Aliases | Do not touch | `toyota` entity block | none (another agent tunes them) |

## Definitions and bases

Every Toyota value states its view and basis in `features` (`view`, `basis`, and `metric` where the id would mislead).
Units are native (¥tn/yr, m units/yr, pct, index); levels are synthetic round priors, never the company's figures.

| View | Total | Parts (residual; eliminations) | Basis |
|---|---|---|---|
| Reporting businesses | `toyota.operating_profit` | automotive, financial services (all other; business-segment eliminations) | segment operating income, IFRS |
| Regional operations | `toyota.operating_profit` | Japan, North America, Europe, Asia (other regions; regional eliminations) | geographic segment operating income by location of the reporting company |
| Regional external revenue | `toyota.net_revenue` | Japan, North America, Europe, Asia (other regions) | external customers only; Japan intersegment revenue is a separate value |
| Revenue by customer location | `toyota.net_revenue` | Japan, North America, Europe, Asia (elsewhere) | location of the external customer |
| Units sold | `toyota.consolidated_units` | Japan, North America, Europe, Asia (other regions) | consolidated vehicle sales by region of sale |
| Units built | `toyota.production_units` | Japan, North America, Europe, Asia (other regions) | production by plant location |
| Retail bridge | `toyota.group_retail_units` | consolidated units (retail through equity-accounted affiliates) | group retail vs consolidated |
| Powertrain | `toyota.vehicle_sales` | hybrid, plug-in hybrid, battery-electric (ICE and other) | Toyota and Lexus retail units; units only |
| Financial services | `toyota.financial_services_operating_income` | revenue, cost of financing (other expenses) | segment, IFRS |
| Pretax bridge | `toyota.pretax_income` | operating income, equity-method income (other finance and non-operating) | income statement, IFRS |
| Net income bridge | `toyota.net_income` | pretax income, income tax (−), minorities (−) | income statement, IFRS |

Rules the build keeps:

- Views of one total overlap. Business segments and regions both sum to operating profit; selling-company and
  customer-location revenue both sum to net revenue. No value is a part of two additive views, and no calibrated
  route reaches a total through the parts of two views (`test_no_calibrated_route_reaches_a_total_through_two_views`).
  Each path lands in one view: regional paths (tariffs, regional growth, pricing, Asia entrants, execution, yen
  components) in the geographic view; product mix and new initiatives in the business view; financing in the
  financial-services composition.
- Accounting links weigh a part by its native sd over the total's (a deduction carries a negative weight); a product
  identity (North America revenue = units × revenue per vehicle) weighs each factor by its log scale over the total's.
  Approximate identities say so (exports ≈ Japan production − Japan sales; imports ≈ North America sales − production).
- Calibrated causal links are only the kept statistical records (m29, s42, s43), the tax formula
  (`ty_tax_formula`, `ty_tax_equity_exclusion`, from the documented effective rate), since Oct 18 the customs
  cost per point of the US rate (`ty_tariff_cost`, from the company's planned tariff cost at the stated rate), and,
  since the [pack round](#pack-round), the yen transaction branch and tariff absorption. Every other causal step is
  uncalibrated: mechanism, sign, conditions, observable, timing, evidence by claim, breaker, unresolved inputs.
- One number per effect: since the pack round the transaction branch carries the dollar transactional effect and m29
  only the remainder (translation, other currencies); translation and imported inputs stay unsized inside it. s42 and s43 summarize the regional-growth and China-affiliates
  paths and are never added to them.
- Subvention is an incentive in automotive and revenue in financial services; it eliminates on consolidation and is
  counted once.
- The workbook forecasts regional operating income as regional revenue × an input margin, with cost rows above EBIT
  display-only and business segments not forecast; no transition cites a workbook cost row as magnitude evidence.

## Second review round

The reviewer's second round (Oct 18) asked five things of every build: source labels that resolve to a document and a
passage; missing inputs that say whether the material was searched; numbers that satisfy the stated financial
relationships; the calculation coverage of each path; and the full method, repeated. The gap register below was
written first, against the state after the first round (commit 6185d7d), and checked with the new tools
(`scripts/construction/check.py --sources --reconcile`, `scripts/construction/inputs.py`).

### Gap register (second round)

| # | Gap | Present before | Add or correct | Evidence or input needed | Test that shows it done | Cat. |
|---|---|---|---|---|---|---|
| R01 | Source ids resolve to a document, but no material claim resolves to a passage | 9 source ids in the local `sources.json`; no `citations.json`; 97 links with a material claim, none cited | A located citation (sheet and cell, or page and lines, with the passage) for every material claim and every baseline value | The documents themselves, re-read | `test_every_material_claim_resolves_to_a_located_citation` | RET |
| R02 | Claims labelled `documented` with no document behind them | `ty.pub`-only claims (credit-loss and residual-loss placement, the equity-method tax exclusion); m29's size labelled documented on a published per-yen sensitivity, which the reviewed sources say is not disclosed; s42 and s43 sizes labelled `model` with no inspected formula | Re-label each claim to its real support (`inferred`, `model`, `assumption`) and cite what does support it | The client's transmission model (`ty.sm`) states what is and is not disclosed | the citation test (no material claim is left without a passage) | MAP |
| R03 | Inputs never searched | 57 `unresolved` entries, all `not_yet_reviewed`; seven were caveats or a history note, not inputs | Search the folder per input; set each status; bind what is found | The workbook, the transmission model, the broker notes, the dashboards | `test_no_input_is_left_unreviewed` | RET |
| R04 | The numbers do not satisfy the identities | At the priors: the net-income bridge off by 1.56%, the powertrain view by 0.19%. At the baselines: operating profit and Toyota and Lexus volume had no level (4 flags); observes rounded | Round priors that add up exactly; the missing totals as baselines; observes at the cells' exact values | The workbook's reported totals | `test_compositions_reconcile_at_the_model_medians`, `test_compositions_reconcile_at_the_local_baselines` | MAP / MC |
| R05 | A size the material supports is left unknown | `ty_tariff_cost` uncalibrated, though the company states its planned tariff cost at the stated rate | Calibrate it with `calibrate.py`; leave every response to it uncalibrated | The planned cost and the rate (company, via `ty.sm`) | `test_tariff_path_has_the_five_transitions` | CAL |
| R06 | Reported exports from Japan exist, but the export value was observed as production minus sales | `toyota.japan_export_units` baseline derived | Observe the reported series; the derivation's gap holds inventory change | The workbook's monthly exports | the citation test (the value's citation is the monthly cells) | MAP |
| R07 | No calculation coverage per path | Forecasts carry `coverage`, but no path reported it | Coverage per path and for the generalization trace (below) | none | recorded here; `test_generalization_trace_japan_production_stoppage` | EXP |

### What changed, by finding

1. **Source labels resolve.** `citations.json` (local) now holds 213 located citations under 159 keys: every one of the
   91 links whose transition makes a material claim, and every one of the 59 values the baselines observe. Each gives
   the source id, the location (sheet and cell, or page and lines of the parsed text), and the passage copied from
   the document (cell label, value and formula; or the text), at most 300 characters. The sources: the company
   workbook (161), the client's transmission model (29), the workbook's operating-income bridge (12), and the two
   broker notes (11). Two source ids were added (`ty.sm`, `ty.rates`), so all 11 resolve; `check.py --sources` reports
   0 unresolved ids, 0 uncited claims and 0 unknown citation keys. Eight links' claims were re-labelled to their real support
   (R02): s42 and s43 magnitude `assumption` (the world's prior statistical records; the client's model states that
   no regional demand elasticity is disclosed); m29 magnitude `model` (the client's per-yen inference from the
   company's results bridges, whose range brackets m29's size; a dry run of `calibrate.py` confirms it, and the size
   is kept as Sally's must channel); `ty_credit_loss_expense` and `ty_residual_cost` existence and direction
   `inferred`; `ty_tax_equity_exclusion` existence and direction `model`; `ty_pipeline_capex` existence `inferred`;
   `ty_robots_external` existence `assumption`. m29's condition observable no longer cites a published sensitivity.
2. **Missing inputs say whether the material was checked.** All 55 inputs (60 entries on 46 links) were searched
   with `inputs.py` over the Toyota folder, the client's spreadsheets and the rates folder (27 files), with extra terms
   where an input's words were narrow, and every candidate was read. Seven caveats were renamed to the inputs they stand
   for, and s44's history note left the list (it stays in the YAML comment and G07). Found and bound: reported exports
   from Japan (now the export baseline), the company bridge's FX split and the client's per-yen inference (citations on
   m29 and the yen branches), the JV reorganization and China equity-method income (citations on the
   China-affiliates links), the robot deployment plan, intersegment revenue by segment, Asia revenue per vehicle, and
   automotive revenue per unit (derivable from two baselines). Found, not bound, each with the reason in its `note`:
   average margins where a contribution margin is needed, brand-basis country sales where the segment is consolidated,
   a broker's gross and net tariff estimates where a price pass-through is needed, and the client's translation proxy.
   Everything else is `not_disclosed_in_reviewed_sources` with the source ids and queries searched. None is
   `not_yet_reviewed`.
3. **The numbers satisfy the stated relationships.** Priors: non-controlling interests and plug-in hybrid volume took
   new round synthetic levels (and the plug-in's accounting weight its new scale ratio), so every additive view adds up
   exactly at the medians. Baselines: operating profit and Toyota and Lexus retail volume were added, every observe
   now carries the cell's exact value, and reported exports replace the derived figure. The table below has the result.
4. **Calculation coverage.** Below, per path and for the generalization trace. One link gained a size from the
   material: `ty_tariff_cost` (calibrated with `scripts/construction/calibrate.py` from the company's planned tariff
   cost at the stated rate, support `guidance`, the range spanning a broker's lower gross estimate and the
   incremental-rate reading). Every response to the cost stays uncalibrated. No other input found supports a size
   without double counting: the per-yen transaction effect would be added to m29, and the margins found are averages.
5. **The method generalizes.** The same steps (register, build, baselines, citations, inputs, reconciliation, view,
   tests, report) ran end to end on Toyota; the generalization trace was re-run against the new state.

### Inputs by status

55 inputs: 10 found and connected, 11 found and not connected, 34 not disclosed in the reviewed sources, 0 not yet
reviewed. Every `not_disclosed` entry lists the source ids and the `corpus:` queries searched; every `found` entry lists
where.

| Status | Inputs (links) |
|---|---|
| found_connected (10) | split of the yen sensitivity by channel (m29); sensitivity to currencies other than the dollar (m29); transactional effect per yen (`ty_yen_transaction`); automotive revenue per unit (s44); Asia revenue per vehicle as a value (`ty_asia_units_rev`); Japan vehicle exports and inventory change as reported (`ty_exports_japan_production`); JV restructuring status and accounting (`ty_china_jv_units`); equity-method income by investee (`ty_jv_units_equity`); intersegment amount by segment (`ty_incentive_subvention`); deployment schedule (`ty_robotics_deploy`) |
| found_not_connected (11) | Asia contribution margin (`ty_asia_rev_oi`); contribution margin per vehicle (`ty_na_rev_to_oi`); depreciation by segment (`ty_capex_auto_oi`); industrial free cash flow excluding financial-services receivable growth (`ty_pipeline_capex`); JV share of China units (s43); pass-through rate (`ty_tariff_reprice`); per-yen translation sensitivity (`ty_yen_translation`); Southeast Asia share of Asia segment units (`ty_asia_share_units`); Toyota share series by country (`ty_chinese_share`); US share of North America segment units (`ty_industry_to_na_units`); US-only sales and production (`ty_imports_na_units`) |
| not_disclosed_in_reviewed_sources (34) | tariffs: covered imported volume by origin, customs value per imported vehicle, parts tariffs on US-built vehicles, US-only import volume by origin, competitor exposure, local capacity headroom, cost gap of local vs Japanese production, transfer-price support from the Japan parent to the US importer, price elasticity by model; volume and price: region-specific magnitude (s42), transaction price per vehicle in North America, fixed-cost base of the North America plants, export margin per unit, share of Japan exports bound for North America, Japan export units by destination region, component exports from Japan to North American plants, wholesale-to-retail timing difference; product: margin by powertrain or model, revenue per unit by powertrain, share of these units retailed by JVs; financing: funding mix, maturity ladder and hedging, finance penetration rate, subvented share of incentives, lease maturity profile, residual assumptions, credit-loss provision line in the financial services segment; execution: launch calendar, quality incidents; group: minority share by subsidiary, translation of other regions' profits; new initiatives: unit cost, committed budget, savings per robot, external revenue from robots |

### Reconciliation

`check.py sally_demo --entities toyota --reconcile --statistic median` and `--baselines
data/sally_data/construction/toyota/baselines.json` (local): total against members + residual + eliminations, each part
signed by its accounting link, tolerance 0.5% of the total. Relative differences only; the levels stay local.

| Composition | Parts (residual; eliminations) | Priors before | Priors now (medians) | Baselines (one fiscal year, actuals) |
|---|---|---|---|---|
| `ty.comp.reporting_segments` | automotive, financial services (all other; eliminations) | 0 | 0 | 0 |
| `ty.comp.regional_operating_income` | Japan, North America, Europe, Asia (other; eliminations) | 0 | 0 | −0.00003% (one unit of the workbook's rounding) |
| `ty.comp.regional_external_revenue` | four regions (other) | 0 | 0 | 0 |
| `ty.comp.revenue_by_customer_location` | four regions (elsewhere) | 0 | 0 | −0.000002% (one unit of rounding) |
| `ty.comp.units_by_customer_region` | four regions (other) | 0 | 0 | 0 |
| `ty.comp.units_by_production_region` | four regions (other) | 0 | 0 | 0 |
| `ty.comp.retail_units_bridge` | consolidated (unconsolidated) | 0 | 0 | 0 (residual derived as the difference) |
| `ty.comp.retail_units_by_powertrain` | hybrid, plug-in, battery-electric (ICE and other) | −0.19% | 0 | 0 (residual derived as the difference) |
| `ty.comp.financial_services` | revenue, cost of financing (other expenses) | 0 | 0 | 0 (residual derived as the difference) |
| `ty.comp.pretax_bridge` | operating income, equity-method income (other) | 0 | 0 | 0 (operating profit had no level before) |
| `ty.comp.net_income_bridge` | pretax, tax (−), minorities (−) | −1.56% | 0 | 0 |

No flag at the priors or at the baselines. Three views close at the baselines by construction (their residual is the
reported total minus the reported parts); the other eight are independent checks of reported parts against a reported
total. **Components and group profit**: at the baselines, reported operating profit equals the business-segment sum
exactly, and the regional sum within one unit of the workbook's rounding (relative 3 × 10⁻⁷); the company's
operating-income change bridge ends within its own rounding of the reported figure (relative 2 × 10⁻⁵). No unexplained
difference is left, so no "unexplained difference" residual was needed; the rounding units are not moved into a
residual, which would misstate a reported line. The first-round differences came from the priors (tax and minorities
summed to more than pretax minus net income) and from totals missing in the baselines. Where a live state observes
a total without its parts (a guidance revision of operating profit), the parts do not move, and the reconciliation at
the model's levels will flag it: the method has no allocation of a total's change to its parts.

### Calculation coverage

Per named path: the trigger is the first step's source, the endpoint the path's. Counts come from
`inference.task.forecast_coverage` on the trigger, with every reached quantified link counted as running (an upper
bound: a forecast also needs the link inside one of its networks) and routes of at most six links; the generalization
row also uses `context.construction.trace`. A link "excluded" carries no size: uncalibrated, with its sign.

| Path | Steps (calibrated / uncalibrated / accounting) | What contributes a calculated size | Excluded (uncalibrated, sign) | Inputs of its steps (by status) | Routes to the endpoint (fully quantified) |
|---|---|---|---|---|---|
| Tariffs and sourcing | 1 / 11 / 5 | `ty_tariff_cost` (rate → customs cost); the identities once a size reaches them | `ty_tariff_reprice` +, `ty_tariff_resource` +, `ty_tariff_absorb` −, `ty_tariff_transfer` −, `ty_list_to_rpv` +, `ty_list_to_units` −, `ty_tariff_base` +, `ty_na_prod_to_exports` −, `ty_na_rev_to_oi` +, `ty_exports_to_intersegment` +, `ty_intersegment_to_japan_oi` + | 11 not disclosed, 2 found not connected | 7 (0): the cost is sized, its effect on profit is not |
| Yen | 1 / 4 / 2 | m29 (aggregate), then the pretax and net-income identities and the tax formula | `ty_yen_transaction` +, `ty_yen_translation` +, `ty_yen_imports` +, `ty_material_japan_oi` −: the decomposition, never added to m29 | 3 found connected, 1 found not connected, 1 not disclosed | 4 (1, m29 direct). Sally's theses S-T1 and S-T3 (the yen moves; Toyota's operating profit is a target): `share_quantified` 0.25 in each, m29 and the group bridge contributing |
| Regional growth (North America) | 0 / 7 / 3 | none of its own steps; s42 (US growth → global retail volume) is the broad summary and never added; the quantified routes run through macro links to USD/JPY and m29 | `ty_us_gdp_industry` +, `ty_industry_to_na_units` +, `ty_na_units_to_production` +, `ty_na_units_to_inventory` −, `ty_inventory_to_units` +, `ty_na_production_to_oi` +, `ty_na_rev_to_oi` + | 3 found not connected, 3 not disclosed | 16 (3, all through the yen) |
| Pricing competition | 0 / 6 / 3 | none | `ty_industry_incentives_match` +, `ty_industry_incentives_conquest` −, `ty_incentive_to_rpv` −, `ty_incentive_to_units` +, `ty_incentive_subvention` +, `ty_na_rev_to_oi` + | 2 not disclosed, 1 found connected, 1 found not connected | 20 (0) |
| Competition from Chinese entrants | 0 / 4 / 1 | none | `ty_chinese_share` −, `ty_asia_share_units` +, `ty_asia_units_rev` +, `ty_asia_rev_oi` + | 3 found not connected, 1 found connected | 2 (0) |
| Product mix | 0 / 7 / 4 | none of its own steps; oil reaches profit through macro links and the yen | `ty_fuel_hybrid` +, `ty_fuel_bev` +, `ty_fuel_ice` −, `ty_hybrid_rev` +, `ty_bev_rev` +, `ty_ice_rev` +, `ty_auto_rev_oi` + | 3 not disclosed | 21 (6, all through the yen) |
| Financing: funding and repricing | 0 / 11 / 4 | none of its own steps; US yields reach profit through macro links and the yen | `ty_ust_funding` +, `ty_funding_cost` +, `ty_funding_reprice` +, `ty_customer_rate_rev` +, `ty_customer_rate_units` −, `ty_customer_rate_arrears` +, `ty_units_receivables` +, `ty_receivables_rev` +, `ty_receivables_borrowings` +, `ty_borrowings_cost` +, `ty_credit_loss_expense` + | 3 not disclosed | 17 (3, all through the yen) |
| Financing: used values, residuals, credit | 0 / 4 / 3 | none | `ty_used_residual` −, `ty_used_severity` −, `ty_residual_cost` +, `ty_credit_loss_expense` + | 3 not disclosed | 2 (0) |
| Execution and share | 0 / 8 / 3 | none | `ty_pipeline_na_share` +, `ty_pipeline_asia_share` +, `ty_pipeline_capex` +, `ty_na_share_units` +, `ty_asia_share_units` +, `ty_asia_units_rev` +, `ty_na_rev_to_oi` +, `ty_asia_rev_oi` + | 3 not disclosed, 4 found not connected, 1 found connected | 9 (0) |
| New initiatives | 0 / 8 / 2 | none | `ty_robotics_rd` +, `ty_robotics_deploy` +, `ty_robotics_capex` +, `ty_robots_savings` +, `ty_robots_external` +, `ty_savings_auto_oi` +, `ty_rd_auto_oi` −, `ty_capex_auto_oi` − | 4 not disclosed, 1 found connected, 1 found not connected | 4 (0) |
| Affiliates: China JVs | 1 / 2 / 4 | from equity-method income on: the pretax and net-income identities and the tax exclusion; s43 sizes volume only | `ty_china_jv_units` +, `ty_jv_units_equity` + | 2 found connected | 4 (0) |
| Group bridge | 1 / 1 / 4 | the identities and the tax formula | `ty_nci_share` + | 1 not disclosed | 3 (2) |
| Generalization: Japan production stoppage | (no path) | the production identity only | every route to profit has an uncalibrated step (13 of 35 traced routes end at operating profit) | (as the links reached) | 4 within six links (0) |

What blocks a size, in short: the responses to a cost or price (pass-through, sourcing, absorption, elasticities)
and the margins on volume, none disclosed; the financing book's gap, residual and credit data, none disclosed; and the
yen's channels, which are found but would double count m29.

### Completion report (second round)

| # | Outcome | What was done, or what blocks it |
|---|---|---|
| R01 | built and verified | 213 located citations, 91 material links and 59 baseline values; 11 source ids resolve |
| R02 | built and verified | eight links' claims re-labelled to their real support, each cited where still material |
| R03 | built and verified | 55 inputs searched: 10 found and connected, 11 found and not connected (reason in each note), 34 not disclosed |
| R04 | built and verified | priors add up exactly at the medians; baselines reconcile within the workbook's rounding |
| R05 | built and verified (one link) | `ty_tariff_cost` calibrated; every response still blocked by a named input (pass-through, elasticity, origin and content) |
| R06 | built and verified | reported exports observed; the derivation's gap is inventory change |
| R07 | built and verified | coverage per path and for the generalization trace (above) |

Counts: 7 second-round gaps (2 retrieval omission, 3 incorrect mapping, 1 missing calibration, 1 export omission,
one of the mapping gaps also missing construction); all 7 built and verified, one of them for a single link. Links
touching Toyota's values: 132 (58 calibrated, of which 51 accounting and 7 causal; 74 uncalibrated).

**What the method could not express for Toyota** (the feedback for the method):

- *A size that belongs to a decomposition.* The per-yen transaction effect is found, but the model holds m29 as the
  calibrated aggregate and the channels as uncalibrated branches; there is no way to calibrate a branch as a share of
  its aggregate without counting the yen twice. A "partition of an aggregate" link type would let the found split be
  used.
- *Moving a total without its parts.* Observing operating profit alone (guidance) leaves the parts where they were, so
  the views stop reconciling; the method has no allocation rule for a total's change.
- *Import of a full baseline set.* Resolved. Since d6e017b an overlap drops only the competing views of that total,
  never parts of other totals, and since the method extension the guard ignores reconciling (`drives: false`) views.
  The baseline bundles pass `scripts/imports/bundles.py check`.
- *Brand-basis versus consolidated-basis series.* The workbook's monthly country data (sales, production, exports) are
  on a brand basis that includes JV units; the segments are consolidated. A value can carry one basis only, so these
  series are found but not connected.
- *Ranges for estimates the client's model labels inference.* The calibration tool takes `documented`, `guidance` or
  `broker` support; a client model's own inference (`model`) cannot be used to size a link, which is the right default
  but leaves the per-yen and per-point inferences as citations only.

## Conversion round

The method gained forms for what is exact but not a sum (Oct 18, [README](README.md#identities-products-ratios-differences)):
identities (products, ratios, differences), stocks and flows, one driving view per total, and state-dependent
responses. Toyota had no conversion tags, so every uncalibrated link was checked against each form.

**One driving view per total.** Operating profit is driven by the regional view (`ty.comp.regional_operating_income`):
the tariff, regional-growth, pricing, Southeast Asia, execution and yen paths feed it, and it is the view the
client's model forecasts. The business segments (`ty.comp.reporting_segments`) reconcile to it: `drives: false`, and
their four accounting links into operating profit are uncalibrated (sign kept, no size). Net revenue is driven by
revenue by selling company (`ty.comp.regional_external_revenue`), which the volume identities feed; revenue by customer
location reconciles, its five links uncalibrated. Every view is still reconciled (`--reconcile`), and the baseline
bundle, which observes both views of each total on one day, now passes `scripts/imports/bundles.py check`.

**Converted, by form.**

| Form | Object | Terms (link ids written with their transitions) |
|---|---|---|
| product | `ty.id.na_revenue` | North America units (`ty_na_rev_units`) × revenue per vehicle (`ty_na_rev_price`): was an accounting pair with hand-set log weights |
| product | `ty.id.japan_revenue`, `ty.id.europe_revenue`, `ty.id.asia_revenue` | units (`ty_japan_units_rev`, `ty_europe_units_rev`, `ty_asia_units_rev`, were uncalibrated) × a new revenue-per-vehicle value per region (generated links) |
| product | `ty.id.fs_revenue` | finance receivables (`ty_receivables_rev`) × contract rate (`ty_customer_rate_rev`), coefficient: the % conversion and lease and other financing revenue as a constant multiple of contract interest (stated as an approximation) |
| product | `ty.id.cost_of_financing` | borrowings (`ty_borrowings_cost`) × funding cost rate (`ty_funding_cost`), coefficient: the % conversion and lease depreciation as a constant multiple of funding interest (approximation) |
| difference | `ty.id.japan_exports` | Japan production (`ty_exports_japan_production`) − Japan sales (`ty_exports_japan_units`) − a new explicit residual, `toyota.japan_other_flows` (inventory build and other flows), so the reported exports and the identity agree |
| difference | `ty.id.na_imports` | North America sales (`ty_imports_na_units`) − North America production (`ty_imports_na_production`) |
| state (sign flip) | `ty_yen_translation` | the translation effect's sign follows the sign of North America operating income (`state.sign_flip` at zero); the link stays uncalibrated |

**Left as they are, with the reason in the link's note:** dealer stock (`ty_na_prod_to_inventory`,
`ty_na_units_to_inventory`, `ty_exports_to_inventory`) is held as days' supply, a stock-to-sales ratio, so a roll-forward
in units does not apply; receivables (`ty_units_receivables`) need a yen flow of new contracts, and the penetration rate
is not disclosed; borrowings from receivables (`ty_receivables_borrowings`) and minorities from pretax income
(`ty_nci_share`) would be one-factor products, which the identity form refuses; tariff pass-through
(`ty_tariff_reprice`) is plausibly asymmetric, but an asymmetry needs sizes on both sides. No disclosed scenario set or
named-peer size applies to Toyota's links, so no scenario or peer calibration was made.

**Links touching Toyota's values, before → after:** 132 → 137 (four generated identity terms; one other company's link
into a Toyota value). Calibrated causal 7 → 7; accounting with a size 51 → 36; identity 0 → 17; reconciling accounting
links without a size 0 → 9; uncalibrated causal 74 → 68 (seven became identity terms; one belongs to another company);
state-dependent 0 → 1.

**Reconciliation now.** At the model's medians every composition is exact and every identity within 0.5% (the
largest gap, North America revenue, 0.2%). At the baselines every composition reconciles as before; six identities hold
exactly (the export identity through its explicit residual, whose size is about 1% of the exports); the two financing
products are blocked, not flagged: the contract and funding rates are not disclosed, so they have no level.

**Coverage now.** Forecasts report a route's own steps apart from summary links. In Sally's theses S-T1 and S-T3,
Toyota operating profit has `share_quantified` 0.25, and every quantified route runs through the summary link m29 only
(own steps quantified: 0). Per path, the route counts in the coverage table above are unchanged: the converted identities
are exact but their inputs (units, rates, receivables) are moved by uncalibrated steps, so no new route is fully
quantified. What the conversion adds is exactness downstream: once a volume or rate step is calibrated, revenue, finance
revenue, cost of financing, exports and imports follow by derived weights.

**What still cannot be expressed.**

- *Paths through the reconciling view carry no size to the total.* Product mix, new initiatives and both financing
  paths land in the business segments; with the regions driving operating profit, a size they gain stops at the segment.
  A matrix would carry it, but no region × business cells are disclosed.
- *A ratio-held stock.* Dealer stock in days' supply cannot accumulate flows; a units stock series is needed.
- *Constant-multiple products.* The financing identities hold lease income and lease depreciation as fixed multiples of
  interest, because the material does not split them.
- *One-factor shares.* Minorities as a share of subsidiaries' profit needs a share value or a two-factor product.

## Pack round

Oct 18: the client added a public document pack for Toyota (152 files: the company's annual reports for two years, its
results decks with transcripts and financial summaries for nine quarters, the US finance subsidiary's annual and
quarterly reports, 25 months of production, sales and export workbooks, the US distributor's sales releases, tariff
statements, certification notices, capital-action notices, integrated reports, Japanese securities reports and a
rating agency's rationale). The bar is [specificity.md](../design/specificity.md) R1–R13 and its Decisions log. The pack
is read as untrusted data (parsed, never executed); every figure from it stays in the local files.

New source ids (each resolves locally to its documents in `sources.json`):

| Id | What it is | Kind of statement (R8) |
|---|---|---|
| `ty.f20`, `ty.f20p` | annual reports, latest and prior year | reported actual |
| `ty.dk` | results presentations with transcripts (operating-income walks, guidance pages) | actual walk lines; guidance pages kept apart |
| `ty.fsum` | financial summaries (statements, segment and geographic tables, the financial-services business apart, share counts) | reported actual; the forecast page is guidance |
| `ty.qa` | Q&A summary of the latest quarter | guidance and commentary |
| `ty.fs10` | US finance subsidiary's annual and quarterly reports | reported actual, US only, another basis |
| `ty.mo` | monthly production, sales and exports by region and country | reported actual, brand basis |
| `ty.us` | US distributor's sales releases | reported actual |
| `ty.tt` | company tariff statements | commentary |
| `ty.cert` | certification-irregularity notices | dated events |
| `ty.cap` | repurchase and dividend notices | actuals (purchases) and resolutions (authorizations) |
| `ty.rt` | a rating agency's rationale | third-party view, never a disclosure |
| `ty.ir`, `ty.ja` | integrated reports; Japanese securities reports (same figures in Japanese) | commentary; reported actual |

### Gap register (pack round)

Written first, against the state after the conversion round (`ccf5059`).

| # | Gap | Present before | Add or correct | Source that unblocks it | Test | Cat. |
|---|---|---|---|---|---|---|
| P01 | Inputs marked not disclosed that the company publishes | 35 not disclosed after searching the sell-side folder | Re-run `inputs.py` over the pack; confirm each candidate by reading it; move statuses | all pack ids | `test_no_input_is_left_unreviewed` | RET |
| P02 | One dated year: no roll-forward or out-of-sample check possible | baselines for FY2026 only, from the client's workbook | A second dated year from the company's own summary; financial-services borrowings observed | `ty.fsum` | `test_fy2025_baselines_reconcile` | MC |
| P03 | No stock-flow for Toyota | none (receivables and dealer stock had reasons in their notes) | Shares outstanding with buybacks, checked between four dated counts | `ty.fsum`, `ty.cap` | `test_shares_roll_forward_between_dated_counts` | MC |
| P04 | The yen size rested on the client's inference (`model`), and no own step was sized | m29 carried the whole effect; branches unsized | Size the transaction branch from the company's own dollar transactional walks; re-size m29 to the remainder (R13 netting) | `ty.dk`, `ty.fsum` | `test_yen_branches_are_separate_and_never_added_to_the_aggregate` | CAL |
| P05 | The tariff cost stopped at the cost value: absorption unsized | only `ty_tariff_cost` sized | Size absorption one for one from the company's walk; grade it `model` (regional split not disclosed) | `ty.dk`, `ty.fsum` | `test_tariff_path_has_the_five_transitions` | CAL |
| P06 | Financing identities blocked at the baselines | blocked by borrowings and the rates | Observe borrowings; test the US subsidiary's rates as proxies out of sample | `ty.fsum`, `ty.fs10` | `test_fy2025_baselines_reconcile` | CAL |
| P07 | Dated one-off events had no place | certification halts, the tariff regime and capital actions unrecorded | A local dated-events file with the production loss computed from monthly data | `ty.cert`, `ty.mo`, `ty.cap`, `ty.dk` | recorded locally (no event form yet) | MC |
| P08 | Region × business matrix | not built: no cells | Search the pack for cells | `ty.f20`, `ty.fsum` | still open | MC |

### Inputs before and after

`inputs.py` parsed 144 of the pack's files (one plain deck PDF does not open; the transcript copy of the same slides
is read instead) with extra terms per input, and every candidate was read before a status moved. Keyword hits that
were not the input (a cyber "penetration test", a derivatives "variation margin") moved nothing.

| Status | Before (conversion round) | After (pack round) |
|---|---|---|
| found and connected | 10 | 10 |
| found, not connected | 11 | 22 |
| found as proxy | 0 | 0 |
| disclosed, not supplied | 0 | 0 |
| not disclosed in the reviewed sources | 35 | 25 (24 of Toyota's own plus a new one, shares reissued from treasury; one is another company's link) |

Moved to found, not connected (11): Japan exports by destination and the share bound for North America (`ty.mo`);
finance penetration, subvened share, funding mix and maturities, the credit-loss provision, residual-value
assumptions and lease maturities (`ty.fs10`, US only, another basis); quality incidents (`ty.cert`, `ty.mo`, recorded as
dated events); translation of other regions' profits (`ty.dk`); minority share by subsidiary (`ty.f20`, ownership only).
Each stays unconnected for a stated reason: the basis differs (US subsidiary or brand basis against the consolidated
segment), or no value holds the figure (a destination split, a subsidiary list). Re-noted with new sources: US-only
sales and production (`ty.mo`, `ty.us`), depreciation by segment and industrial cash flow (`ty.fsum`), the per-yen
translation sensitivity (still none disclosed: the annual report gives FX value-at-risk), and pass-through (the company
states it gives none). Still not disclosed after the pack: covered imports by origin and customs value, parts tariffs
on US-built vehicles, transfer-price support, elasticities, unit and powertrain margins, transaction prices, launch
calendar, capacity headroom, and dealer days' supply (not in the US releases).

### Calibrations added

| Link | Before | After | Evidence |
|---|---|---|---|
| `ty_yen_transaction` (USD/JPY → Japan operating income) | uncalibrated | calibrated, `documented`: jointly over eight actual periods (`calibrate.py --disclosure`), each the dollar transactional walk line against the average-rate change, annualized; forecast walks excluded | `ty.dk` |
| m29 (USD/JPY → operating profit) | calibrated, `model` (client inference) | calibrated, `inferred`: the remainder of the company's total FX effect after the dollar transactional line, over the same eight periods (R13 netting, recorded in its note) | `ty.fsum`, `ty.dk` |
| `ty_tariff_absorb` (tariff cost → North America operating income) | uncalibrated | calibrated one for one in yen, `model`: the company reports the tariff impact inside consolidated operating income; its regional split is not disclosed | `ty.dk`, `ty.fsum` |
| `ty_tariff_cost` | calibrated, guidance | unchanged size; now cited to the company's own deck and the latest quarter's revision (a revision is news, R8) | `ty.dk`, `ty.qa` |
| `ty_buyback_shares` (shares repurchased → shares outstanding) | none | stock-flow link (derived weight) | `ty.cap`, `ty.fsum` |

Considered and not sized: the US finance subsidiary discloses a ±100bp scenario on both sides (asymmetric), but on
pre-tax cash flow, for the US book only, and immaterial at group scale; a new reduced form from US rates to the
segment would be sized from another basis, so it is recorded locally, not built. The translation and euro lines stay
inside m29's remainder: the world has no EUR/JPY value, and the translational line pools every currency.

**R13 netting for the yen.** Before, m29 carried the whole effect and no branch had a number. The company's walks now
size the dollar transaction branch directly, so the reduced form keeps only what the branch does not represent:
total FX effect minus the dollar transactional line, regressed on USD/JPY (`inferred`). m29 cannot be retired: it is
Sally's must channel. A forecast route through the transaction branch and one through m29 now count different parts of
the effect, never the same part twice.

### Reconciliation at the new baselines

| Bundle (local) | Compositions | Identities | Roll-forwards |
|---|---|---|---|
| FY2026 (workbook, plus borrowings from the company's summary) | 11 of 11 within rounding | 6 hold exactly; the two financing products blocked by their rate alone | — |
| FY2025 (company summary as first published) | the six money views within rounding; five unit views blocked (no FY2025 units in the bundle) | all blocked (unit levels or rates missing), none flagged | — |
| Shares (four dated counts, three windows) | — | — | `ty.sf.shares` within 0.05% in every window |

The financing identities: the US subsidiary's funding rate and portfolio yield, used as proxies, track the direction
between the two years but miss the level change by several percent out of sample, because the consolidated book is not
the US book. Per the Decisions log they stay in the local estimates file, and the identities stay blocked, naming the
rate. Financial-services borrowings and receivables now have two dated levels each, but their roll-forward is not
built: proceeds and repayments are disclosed, the translation of the foreign-currency book is not, so the check would
measure FX rather than test the structure.

### Coverage now

| | Conversion round | Pack round |
|---|---|---|
| Links touching Toyota's values | 137 | 138 |
| Calibrated (incl. identity and stock-flow weights) | 60 | 63 |
| Uncalibrated | 77 | 75 |
| Stock-flow links | 0 | 1 |
| S-T1, Toyota operating profit: quantified routes | 3 of 12, all through m29 only | 6 of 12; 3 through Toyota's own steps |
| S-T1: own steps quantified | 0 of 3 | 1 of 3 (transaction) |
| S-T3: quantified routes | 2 of 8 | 4 of 8; 2 through own steps |
| Paths with a calibrated causal step | yen 1, tariffs 1 | yen 2, tariffs 2 |

The tariff route (rate → customs cost → North America operating income → operating profit) is now quantified end to
end on Toyota's own steps; the management responses (price, sourcing, transfer price) and the customer response stay
unsized.

### Emily's points: what the pack closes and what stays open

Closed or narrowed: an own step sized beside the reduced form without double counting (R13); dated history beyond
one year for the money views and four dated share counts; event times for the certification halts with their
production loss; guidance and revisions kept apart from actuals; primary documents ranked above third-party views
(the rating rationale is searched, not used).

Still open:

- *Most operating steps.* Pass-through, elasticities, incentive response, transfer-price support and margins are not
  disclosed in the pack either.
- *Region × business matrix.* The geographic segments are all-business; no cells are disclosed, so paths that land
  on the business view still cannot reach operating profit with a size.
- *Financing.* The consolidated funding rate, contract rate and credit loss rate are not disclosed; the US
  subsidiary's figures are another basis. The financing identities stay blocked.
- *Events as a form.* The dated events are recorded locally; the engine has no event form yet to replay them.
- *Two to three years of history.* Two dated years of money levels and four share counts are in; units for the
  earlier year are not in the bundle (the summary's unit table parses out of order; the monthly workbooks are on a
  brand basis), and earlier years would need the prior summaries.

## Plan round

Oct 18: the reviewer's build plan for Toyota and Tokio Marine (distilled into [specificity.md](../design/specificity.md):
the build order, R14–R16 and the Decisions rows). It names eight Toyota areas and asks for them in order:
composition, then operating paths, then financial mapping, then calibration. It also asks for four reviewable parts,
which follow. Every figure stays in the local files; this page holds ids, structure and counts. The build is checked
in `sally_demo` and in the focused world `sally_focus` (Toyota and Tokio Marine, [focus.md](focus.md)).

### Part 1. Before/after audit by canonical id

What Toyota owned before this round was checked first, in the internal model and not only in the export. Each item is
classified as owned, missing, modify lightly, or do not touch.

| Area | Owned (reused) | Missing (added) | Modify lightly (corrected) | Do not touch |
|---|---|---|---|---|
| Business composition | 11 compositions: segments, regions, selling-company and customer-location revenue, units sold and built, retail bridge, powertrain, financial services, pretax and net-income bridges; equity-method income for material affiliates; dated FY2025 and FY2026 baselines | `ty.comp.segment_revenue` (each business with its inter-segment sales, and the eliminations that make them external; reconciling view of net revenue); `toyota.other_business_revenue`, `toyota.segment_revenue_eliminations`; 4 reconciling links | `test_no_calibrated_route_reaches_a_total_through_two_views` checks every pair of views (net revenue has three) | the driving views (regions for operating profit, selling company for net revenue) |
| Tariffs and sourcing | `ty.path.tariffs_sourcing`, `ty_tariff_cost` (guidance), `ty_tariff_absorb` (model), reprice, resource, transfer branches | `toyota.us_customs_base`; `ty_exports_customs_base`, `ty_customs_base_cost` (duty due at customs entry; who pays), `ty_tariff_incentives` (a fifth response) | `ty_tariff_base` re-routed from the tariff cost to the customs base, with an R14 note (regional imports are not the customs base); dealer stock and plant absorption steps added to the path; path description made operational | m29, s42, s43 sizes; the tariff cost's guidance size |
| Pricing and incentives | `ty.path.pricing_competition` (match, hold price, realized price, volume, subvention) | `ty_dealer_stock_incentives` (dealer response) | path description: management's walk line "marketing efforts" stays one aggregate (R14) | — |
| Product mix and demand | `ty.path.product_mix` (customer choice), powertrain view | `toyota.electrified_supply_capacity`, `ty_supply_hybrid`, `ty.path.supply_availability` | — | margins by powertrain stay absent (a sales share is not a margin) |
| Yen exposure | transaction, translation and imported-input branches; m29 remainder (R13 netting) | local per-period reconciliation to the disclosed aggregate FX impact | `ty_yen_imports` note: the dollar part is inside the net transactional line; path description states the reconciliation | m29's link and must-channel role |
| Financial services | funding, repricing, credit, residual paths; the financing identities (blocked) | `toyota.us_finance_subsidiary_earning_assets`, `ty_us_finance_scope` (subsidiary to its consolidation scope, not a composition part); `ty.path.financing_borrower` | — | the financing identities' constants (proxies are another basis) |
| Production disruption | dated events (local); the Japan export identity | `toyota.certification_shortfall`, `toyota.recovery_costs`; `ty_cert_production` (sized by definition), `ty_cert_deliveries`, `ty_cert_recovery`, `ty_recovery_costs_oi` (graded model), `ty_japan_production_to_oi`; `ty.path.production_disruption` | — | the generalization trace from Japan production (still no path starts there) |
| Cash and capital | shares stock-flow `ty.sf.shares`, buybacks | `toyota.industrial_operating_cash_flow`, `toyota.industrial_free_cash_flow`, `toyota.industrial_liquidity`, `toyota.dividend_per_share`, `toyota.dividends_paid`, `toyota.buyback_authorization`; identities `ty.id.industrial_fcf` (difference) and `ty.id.dividends` (product); `ty.path.cash_capital` | — | the finance book's own funding (`ty_receivables_borrowings`), kept out of industrial cash |

Counts, before → after: compositions 11 → 12; paths 12 → 16; identities 8 → 10; stock-flows 1 → 1; values +13;
links touching Toyota 138 → 163 (calibrated, incl. accounting, identity and stock-flow weights, 63 → 69; uncalibrated
75 → 94). Inputs: found and connected 10 → 10, found not connected 22 → 23, not disclosed 25 → 34 (the new steps'
inputs, each searched over the supplied material and the pack). Not representable in the schema, flagged rather than
forced: a walk line (a period-on-period change) as a value; an event as a form the engine replays; a threshold that
follows a moving level (the liquidity buffer); a product whose base has no level (duty = customs base × rate is held
as a signed step beside the sized reduced form).

### Part 2. Composition and connected paths

Each path below runs from its trigger to a financial endpoint; the steps, transitions and sizes are in the
[readable view](#readable-view).

| Area | Path | Trigger → operational steps → accounts | Endpoint |
|---|---|---|---|
| Tariffs | `ty.path.tariffs_sourcing` | US rate → customs base (fed by North America imports and US-bound Japan exports, neither the base itself) → duty at entry, paid by the US importer → absorb / reprice / trim incentives / resource / transfer price → realized price, lost volume, dealer stock, local production and plant absorption → North America and Japan operating income | operating profit (regional identity) |
| Pricing | `ty.path.pricing_competition` | rivals' incentives → match or hold price, subvention; dealers lift incentives when stock builds → realized net price and volume → North America revenue and operating income | operating profit |
| Product mix | `ty.path.product_mix`, `ty.path.supply_availability` | fuel economics (choice) or electrified capacity (supply) → powertrain units → automotive revenue → automotive operating income | operating profit through the business view (reconciling, no size reaches the total) |
| Yen | `ty.path.yen` | USD/JPY → transaction (Japan), translation (North America, sign follows its profit), imported inputs (inside the net transactional line); m29 the remainder | operating profit |
| Financial services | `ty.path.financing_funding`, `ty.path.financing_borrower`, `ty.path.financing_credit_residual` | funding rates → funding cost and repricing → financing revenue and cost; borrower conditions → credit losses; used values → residual losses → segment income; the US subsidiary maps to the segment's book | operating profit through the business view |
| Production disruption | `ty.path.production_disruption` | certification restriction → production withheld → deliveries, plant utilization, exports (identity), recovery costs → Japan operating income | operating profit |
| Cash and capital | `ty.path.cash_capital` | earnings → industrial operating cash → free cash flow (identity) → liquid assets → dividends (identity) and buybacks under an authorization → shares outstanding (stock-flow) | shares outstanding |
| Composition | `ty.comp.segment_revenue` and the 11 earlier views | business, region, customer location, production location and product kept as separate views; one drives each total | net revenue, operating profit |

### Part 3. Evidence and calibration

| Item (local, under `data/sally_data/construction/toyota/`) | What it holds | Check |
|---|---|---|
| `baselines.json`, `baselines_fy2025.json` | two dated fiscal years from the company's own summaries; segment revenue, cash and capital added this round | every money view reconciles; the dividend identity holds at both years (0.3% at the earlier, from record-date shares); free cash flow blocked (no reported level, never derived from its own identity) |
| `shares.json` | four dated share counts and the repurchases between them | `ty.sf.shares` within 0.05% in each of three windows |
| `history.json` (R15) | eight standalone quarters of units by region (sold and built), revenue and operating income by region and segment, average FX rates, from the company's quarterly tables; walk components derived standalone from cumulative figures | every quarterly row adds to its fiscal years; regions and segments add to the group each quarter within rounding; each derived quarter equals the reported quarter (27 of 27); four breaks kept (a deconsolidation, a walk-definition change, cumulative workbook reporting, the GAAP switch) |
| `fx_reconciliation.json` | per actual period: the transactional line and its currency parts, the total FX effect, the translational remainder | transactional = dollar + euro + other in all eight periods; transaction branch + m29 remainder = the disclosed total |
| `bindings.json` (R15) | 63 workbook bindings with version, tab and cell, cell content, and the downstream formula each feeds | all are historical levels; none binds a displayed cost row as a sensitivity (the workbook's cost rows above EBIT are display-only; EBIT is the regional sum of revenue × input margins) |
| `events.json` | dated certification halts with the measured production loss; the tariff regime and its revision; the buyback authorization | event dates in order; loss computed by a stated method (inferred) |
| `estimates.json` | the US subsidiary's rates as proxies, with the out-of-sample test | not observed into baselines (another basis) |
| `citations.json`, `sources.json` | a located passage for every material claim; 23 source ids in use | `check.py --sources`: 0 unresolved, 0 uncited |

Calibrations this round: `ty_cert_production` (one for one in units, by definition of the value; documented) and
`ty_recovery_costs_oi` (one for one in yen; graded model because the regional booking is inferred). The quarterly
history was assembled and checked; it was not used to fit any link by co-movement (R4): no step's size rests on a
correlation.

Unresolved inputs that block sizes, by area: tariffs (covered imports by origin, customs value per vehicle, parts
tariffs, pass-through, incentive spend per unit); pricing (dealer days' supply, transaction prices, elasticities);
product mix (electrified capacity and backlog, margins by powertrain); financial services (consolidated funding and
contract rates, the US share of the book on one basis, provisions by segment); disruption (deliveries lost per unit,
recovery costs by event, the Japanese fixed-cost base); cash and capital (the liquidity buffer, cash conversion).

### Part 4. End-to-end checks

Three validation cases, each posed as a forecast in the internal model, read in the export (`/context/v4`, and the
focused export written locally by `scripts/imports/export_context.py sally_focus`), and traced through the
construction endpoint an agent reads (`/construction/toyota/trace`), in both worlds:

| Case | What is calculated | What is direction only, and why | Test |
|---|---|---|---|
| Tariff absorption versus price recovery (a higher US rate) | rate → cost (guidance) → North America operating income (absorption, model) → operating profit and on to net income | reprice, trim incentives, resource and transfer price: uncalibrated (pass-through and elasticities not disclosed); listed as excluded, never zero | `test_validation_tariff_absorption_versus_price_recovery` |
| Financing pressure (US 2-year yield up) | the yen route the rate move sets off (m29 remainder and the transaction branch) | every financing step: the consolidated funding rate is not disclosed and the subsidiary's scenario is another basis; financial-services income has 0 quantified routes, and the brief says so | `test_validation_financing_pressure` |
| Outside both: a North American plant stoppage (no path written for it) | imports by identity, production volume by identity | plant absorption, the duty base, North America profit: uncalibrated steps, named | `test_validation_outside_the_cases_north_american_plant_stoppage` |

In the focused export, each case's links are present with their transitions, calibrated links carry a size and
uncalibrated ones none, and all 16 Toyota paths and 12 compositions are exported.

## Batch 2

Oct 18: the reviewer's second Toyota batch. It has three parts. The first is workbook repairs (W1–W6). The second is
builds that answer the open questions (Q7–Q16). The third is a golden bank of 30 seed questions in ten categories,
meant to test the world model directly, before the scenario agent is attached. Ten seeds were run, one per category.
Every figure stays local: `data/sally_data/construction/toyota/` holds the workbook check, provenance and ledgers, and
`data/sally_data/golden/` holds the bank and the graded answer records. This page holds ids, structure and counts.

**The workbook copy.** All eight cells the reviewer quotes match our copy, in both its values and its formulas (local
`workbook_check.json`, 2,172 cells read). The file hash differs from the one the reviewer cites. The cited content is
the same, so the likeliest cause is a re-save or a later version of the file; this is one question for the reviewer.
The workbook was read, never modified, and nothing in it was executed.

### A. Before/after record

| Area | Already owned (reused) | Missing (added) | Modified lightly | Left alone |
|---|---|---|---|---|
| W1 baseline and export reconciliation | `ty.comp.reporting_segments`, `ty.comp.regional_operating_income` | each baseline's provenance: raw source, normalized amount, model update, reason (local); an observation's `occurred_at` in v1 (the reported period end, apart from publication and recording) | - | the workbook; actuals are never plugged into "other" |
| W2 assumption ledger | the input statuses on every link | an assumption ledger of 29 rows, 5 of them unknown-coverage text cells read as zero (local) | - | "fact" labels in the workbook are not taken as facts |
| W3 sensitivity overlap | `ty_yen_transaction`, m29 | the disclosure files for the re-solve (local) | both re-solved on standalone, non-overlapping quarters; before and after are in their notes | - |
| W4 broker means | - | a broker comparison view (local), never forced into an identity | - | mean net income is never divided into mean EPS |
| W5 periods | `ty.sf.shares` | certification, tender, cancellation and authorization as separate dated events; annual controls kept apart from quarter sums (local) | - | - |
| W6 retrieval | transitions on 196 of 197 links | a retrieval profile on every link, in the export and in v1 (`Relationship.profile`): native slope, exposure, unit, date, hedge, pass-through, financial endpoint, calculation, source | - | - |
| Q7 customs | `toyota.us_customs_base`, `toyota.us_tariff_cost` | `ty.id.us_duty` (duty = covered value × rate), `ty.comp.us_customs_base_by_origin` (Japan, North America, third country) | `ty_tariff_cost`, `ty_customs_base_cost` became identity terms | - |
| Q8 transfer price | `ty_tariff_absorb` | `toyota.tariff_transfer_support`; `ty_transfer_support_na` (+1) and `ty_transfer_support_japan` (−1), which net to zero at the group | `ty_tariff_transfer` re-targeted to the support | - |
| Q9 incentives | `ty_incentive_to_units` (unsized) | `ty.id.na_incentive_cost`, `ty.id.incentive_breakeven`, held in dollars | `ty_incentive_cost_fx` removed: the yen is a stated conversion | - |
| Q10 dealer days | `toyota.na_dealer_inventory` | `ty.id.dealer_days` (365 × stock / annual sales), `ty.sf.na_dealer_stock` | the inventory links re-targeted to arrivals | no synthetic level is presented as observed |
| Q11 finance | `toyota.us_finance_subsidiary_earning_assets` | the US module: `ty.id.us_fin_income`, `ty.id.us_fin_expense`, `ty.id.us_fin_nii`, `ty.id.fs_us_scope`, asset and funding clocks, `toyota.fs_income_uncovered`, `ty.comp.fs_by_scope` (reconciling), `ty.path.us_finance_module` | - | the group book is never repriced at US rates |
| Q12 aggregation | one driving view per total; a total is found once when two routes reach it | - | - | - |
| Q13 substitution and capacity | `ty.comp.retail_units_by_powertrain`, `ty.path.supply_availability` | - | - | the binding minimum of two constraints is a schema gap (E) |
| Q14 elimination | `ty.comp.segment_revenue` (reconciling), `ty_incentive_subvention` (unsized) | transfer support that nets to zero (Q8) | - | - |
| Q15 liquidity | `toyota.industrial_liquidity`, `toyota.buyback_authorization` | `ty.sf.industrial_liquidity`, `toyota.buyback_spend`, `toyota.industrial_other_cash_movements` | `ty_fcf_liquidity`, `ty_dividends_liquidity` became stock-flow terms | buybacks stay a board decision, not a formula |
| Q16 earlier history | the FY3/26 baselines | FY3/25 annual unit controls and the sum of quarters, kept apart (local) | - | - |
| Seeds (Part 3) | - | `ty.id.us_brand_units` (US market × brand share, with no link onward to consolidated units); `ty.id.eps` (net income / weighted-average shares, `toyota.weighted_average_shares`); `ty.id.us_translation` (dollar profit × average rate) | `ty.path.production_disruption` gained an inventory-buffer branch (`ty_exports_to_inventory`, `ty_arrivals_stock`) | - |

In total, Toyota now has 197 links: 101 calibrated, 96 uncalibrated, 54 accounting, 43 identity and 7 stock-flow. It
also has 21 identities, 14 compositions and 17 paths. `check.py` reports no problems and no uncited material claims.

### B. Corrected baselines and provenance

- **Dated actuals.** The FY3/26 baselines are imported through v1 bundles and changes, so they become dated
  observations, not part of the model state. Each observation now carries its `occurred_at` (the period end) apart
  from `valid_at` (publication) and `observed_at` (recording). A question about "the baseline" can then name its
  period.
- **Views reconcile at that period.** At the period end, the business view and the regional view each reconcile to
  group operating profit; they differ by one rounding unit. Neither is ever added to the other.
- **State versus actual.** The model's state of a total differs from its actual, and answers report the two apart.
- **Provenance.** Each baseline's provenance (source, cell, raw amount, ÷1000, model update, reason) is in local
  `baseline_provenance.json`. Reconciliation is re-run after each import. The figures stay local.

### C. Connected scoped finance modules and paths

- **US finance module.** `ty.path.us_finance_module` has 9 steps, in two branches:
  - an asset clock: `ty_ust_us_asset_yield` → `ty_usfin_yield_income`;
  - a funding clock: `ty_ust_us_funding_rate` → `ty_usfin_rate_expense`.

  Both meet at the margin (`ty.id.us_fin_nii`), which is translated into the segment's US scope
  (`ty.id.fs_us_scope`). The segment's other income is an explicit residual, `toyota.fs_income_uncovered`; it is
  never a plug, and the scope view `ty.comp.fs_by_scope` reconciles rather than drives. A rate shock reprices only the
  share of each balance that resets, for the time it is active. The reset shares are synthetic priors and are listed
  in E.
- **Tariffs** (`ty.path.tariffs_sourcing`). The customs base by origin feeds the duty identity, and the duty
  reaches North America income (`ty_tariff_absorb`). Transfer support moves profit between regions and recovers
  nothing at the group. Pricing, incentives and re-sourcing are parallel responses that stay unsized.
- **Production disruption** (`ty.path.production_disruption`). Fewer exports arrive at dealers, and the dealer
  stock buffers sales through the mass balance.
- **Group bridge** (`ty.path.group_bridge`). Operating profit → pretax income → tax and minorities → net income;
  EPS then follows by `ty.id.eps`. Share price is reached only by a default coefficient, which is not a valuation model.

### D. Seed responses

The harness is `src/axelrod_wm/evaluation/golden.py`, with the CLI in `scripts/evaluation/golden.py`.

- **The responder** sees only the question and the fixture. It answers through v1 reads only: search, the
  construction, relationships with their profiles, traces and observations. Its arithmetic is the model's identities,
  stock-flows and native slopes, applied to the fixture's inputs, which are given in model ids.
- **The grader** sees the hidden spec. It scores four outcomes separately and lists critical failures (sign, scope,
  unit, accounting) on their own. Workbook cell locations are reported as "Not tested", because they are bound in the
  local provenance, not in the model.
- **Unit tests** (`tests/unit/evaluation/test_golden.py`) use synthetic cases only.
- **Records.** The bank (all 30 seeds, verbatim, with hidden reference blocks) and the answer records are local. The
  seeds were run in `sally_demo` and `sally_focus`, with the same grades in both.

| Seed | Category | Evidence | Mechanism | Calculation | Timing | Why |
|---|---|---|---|---|---|---|
| T01A | baseline | Pass | Pass | Pass | Partial | both views reconcile at the period end, and the actual is reported apart from the state; guidance and broker means are not records in the world (local only) |
| T02A | demand and share | Partial | Pass | Pass | Pass | units = market × share, decomposed into market and share effects; not sent into consolidated units; the North America share link was not retrieved from the question's wording |
| T03A | pricing | Pass | Pass | Pass | Pass | the direct concession through the incentive identity, converted at the stated rate; the volume response is held constant and named |
| T04C | supply | Pass | Pass | Pass | Pass | the mass balance per quarter and cumulatively; units only, no profit |
| T05A | costs | Pass | Pass | Pass | Pass | gross, hedge offset, exposure and recovery stated apart; recovery applies after hedges |
| T06B | financing | Pass | Pass | Pass | Pass | asset and funding clocks on the US module, for a full year and a half year; the lease book is not scaled |
| T07B | currency | Pass | Pass | Pass | Pass | a profit and a loss translate with opposite deltas; the aggregate FX total is not added |
| T08B | tariffs | Pass | Pass | Pass | Pass | North America and Japan move by the allocation, the group by the duty alone; pricing and incentive responses are listed as unsized |
| T09C | earnings | Pass | Pass | Pass | Pass | operating profit → net income → EPS at the stipulated tax rate and share count; no return is calculated |
| T10A | unknowns | Pass | Pass | Pass | Pass | operating profit is "unknown or unimplemented", with the unsized links listed; no measured zero |

No critical failure occurred.

The first graded run had four Fails, two from harness defects and two from model gaps:

- T01A: the observations carried no period, and the baselines had not been driven in;
- T04C: the disruption path had no inventory buffer;
- T08B: a feedback loop was never resolved (harness);
- T10A: the market links sat outside the entity filter (harness).

All four were fixed and the seeds re-run.

The other three Part 3 gaps (US brand units, EPS, translation) were found by reading the seeds and added before that
run. No answer is hardcoded: each arithmetic step is the model's own object.

### E. Residual data

| Field | Scope and date | Where searched | Why it matters | Bounded assumption? |
|---|---|---|---|---|
| US industry volume and Toyota brand share on one denominator | US light vehicles, FY3/26 onward | `ty.wb`, `ty.us`, `ty.peer` | units = market × share needs a like-for-like base (T02A) | yes: a fixture |
| Incremental units per incentive dollar; contribution per incremental unit | North America, FY3/27 | `ty.wb` marketing bridge (aggregate), `ty.fsum` | the net outcome of a promotion (T03A, T03B) | yes: a PM range |
| Hybrid and ICE contribution per unit, consolidated perimeter | by region, FY3/27 | `ty.wb`, `ty.xc`, `ty.peer` | a mix shift's profit (T04A) | yes |
| Plant-level loss, usable inventory and catch-up by region | by plant and quarter | `ty.mo`, `ty.cert`, `ty.wb` | delayed versus foregone units (T04B, T04C) | yes: the dealer stock stands in |
| Purchasing hedge cover and supplier pass-through by input | Japan materials, FY3/27 | `ty.wb` (aggregate proxy only), `ty.f20` | net cost and its timing (T05A, T05B) | yes |
| Share of US finance assets and debt that reprices within a year; swaps | US subsidiary, FY3/26 | `ty.fs10` (sensitivity, not a schedule) | the clocks are synthetic priors now (T06B) | yes, from the maturity tables |
| Contract and funding-rate schedule outside the US | Japan and other regions | `ty.f20`, `ty.fsum`, `ty.wb` | the uncovered residual of the finance segment (T06A) | partly |
| Dollar profit of US subsidiaries apart from the North America segment | US, FY3/26 | `ty.f20` geographic note | translation without the segment's non-dollar parts (T07B) | yes: a fixture |
| Transfer-price changes actually set | Japan parent to US importer | `ty.f20`, `ty.tt` | the regional split of a duty (T08B) | yes: a scenario allocation |
| Diluted weighted-average share path; effective tax rate | group, FY3/27 | `ty.f20`, `ty.cap`, `ty.wb` | the NI and EPS bridge (T09A, T09C) | yes |
| GDP and unemployment elasticities of volume | by region | `ty.wb` (marked not disclosed), `ty.sm` | the unsized macro branch (T10A) | yes: a PM assumption, labelled |
| Declared customs value by origin, category and entry date | US, FY3/26 onward | `ty.tt`, `ty.mo`, `ty.wb` | the duty identity has no observed base (T08A) | yes |

Schema gaps, flagged rather than built:

- **The minimum of two constraints.** A buyback is capped by both the remaining authorization and what is
  affordable; a delivery is capped by both orders and capacity. Neither binding minimum can be stated yet.
- **Guidance and broker estimates as dated non-actual records.** The world has no such record kind, so they stay
  local (T01A).
- **Search on question wording.** It does not reach every relevant value (T02A).

## Readable view

Generated by `scripts/construction/check.py sally_demo --entities toyota` from the loaded model (the same objects the
API serves at `/v1/world-models/sally_demo/entities/toyota/construction`). Chains mark a step whose size is unknown with `?`; "Size" shows
the accounting weight or calibrated effect in sd per sd, and "unknown" for uncalibrated links. The version with
workbook levels and traces is local (`data/sally_data/construction/toyota/view/`).

163 links touch its values: 69 calibrated, 94 uncalibrated (represented, size unknown), 49 accounting, 21 identity, 1 stock-flow; 1 state-dependent; 162 carry a transition.

### Business composition

#### financial services: financial services segment (IFRS) (¥tn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Toyota financial services revenue | `toyota.financial_services_revenue` |
| Toyota cost of financing operations | `toyota.fs_cost_of_financing` |
| Residual: Toyota financial services other expenses | `toyota.fs_other_expenses` |
| **Total: Toyota financial services operating income** | `toyota.financial_services_operating_income` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Lending and leasing income less funding interest, lease depreciation and residual impairment, and other expenses (credit-loss provisions assumed here). Revenue includes intersegment subvention, eliminated at group level.

#### reporting segments: consolidated income statement, IFRS (¥tn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Toyota income before income taxes | `toyota.pretax_income` |
| Toyota income tax expense | `toyota.income_tax_expense` |
| Toyota income attributable to non-controlling interests | `toyota.noncontrolling_interests` |
| **Total: Toyota net income attributable to owners** | `toyota.net_income` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Tax and minorities are deducted (negative accounting weights).

#### reporting segments: consolidated income statement, IFRS (¥tn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Toyota operating profit | `toyota.operating_profit` |
| Toyota share of equity-method income | `toyota.equity_method_income` |
| Residual: Toyota other finance and non-operating income | `toyota.other_nonoperating_income` |
| **Total: Toyota income before income taxes** | `toyota.pretax_income` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Equity-method income (JVs and affiliates) and finance and FX items sit below operating income.

#### regions: revenue from external customers by location of the selling company (IFRS; excludes intersegment) (¥tn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Toyota Japan external revenue | `toyota.japan_external_revenue` |
| Toyota North America external revenue | `toyota.north_america_external_revenue` |
| Toyota Europe external revenue | `toyota.europe_external_revenue` |
| Toyota Asia external revenue | `toyota.asia_external_revenue` |
| Residual: Toyota other regions external revenue | `toyota.other_regions_external_revenue` |
| **Total: Toyota net revenue** | `toyota.net_revenue` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
External customers only, so no elimination: rank regions on this, not on total regional revenue, which includes intersegment sales (Japan's intersegment revenue is its own value, internal supply).

#### regions: operating income by geographic segment, location of the reporting company (IFRS, before eliminations) (¥tn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Toyota Japan operating income | `toyota.japan_operating_income` |
| Toyota North America operating income | `toyota.north_america_operating_income` |
| Toyota Europe operating income | `toyota.europe_operating_income` |
| Toyota Asia operating income | `toyota.asia_operating_income` |
| Residual: Toyota other regions operating income | `toyota.other_regions_operating_income` |
| Eliminations: Toyota regional eliminations | `toyota.regional_eliminations` |
| **Total: Toyota operating profit** | `toyota.operating_profit` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
By location of the reporting company. Japan's profit includes its export margin on vehicles sold to overseas subsidiaries (intersegment); North America's includes its finance arm. Overlaps the business view: never add the two.

#### reporting segments: segment operating income by business (IFRS, before intersegment eliminations) (¥tn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Toyota automotive operating income | `toyota.automotive_operating_income` |
| Toyota financial services operating income | `toyota.financial_services_operating_income` |
| Residual: Toyota all other businesses operating income | `toyota.other_business_operating_income` |
| Eliminations: Toyota business-segment eliminations | `toyota.segment_eliminations` |
| **Total: Toyota operating profit** | `toyota.operating_profit` |

A reconciling view: its parts are observed and reconciled against the total but carry nothing into it, so it can be imported alongside the driving view without counting a change twice.
Automotive and financial services earn differently (vehicle margin versus lending spread, credit and residual risk) and use capital differently. This is the view a business mechanism lands in; the regional view of the same total is never added to it.

#### customer location: group retail units versus consolidated vehicle sales (m units/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Toyota consolidated vehicle volume | `toyota.consolidated_units` |
| Residual: Toyota retail volume through equity-accounted affiliates | `toyota.unconsolidated_retail_units` |
| **Total: Toyota group retail volume** | `toyota.group_retail_units` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Units retailed by equity-accounted JVs (mostly China) count in retail volume but reach the accounts only as equity-method income, not consolidated revenue.

#### product: Toyota and Lexus retail units by powertrain (includes units retailed by equity-accounted JVs) (m units/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Toyota hybrid retail volume | `toyota.hybrid_retail_units` |
| Toyota plug-in hybrid retail volume | `toyota.plugin_hybrid_retail_units` |
| Toyota battery-electric retail volume | `toyota.battery_electric_retail_units` |
| Residual: Toyota ICE and other retail volume | `toyota.ice_and_other_retail_units` |
| **Total: Toyota global vehicle sales** | `toyota.vehicle_sales` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Units only. Margins by powertrain are not disclosed and are not invented here; an electrified share is not a measured hybrid profit.

#### customer location: revenue by location of the external customer (IFRS) (¥tn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Toyota revenue from customers in Japan | `toyota.japan_customer_revenue` |
| Toyota revenue from customers in North America | `toyota.north_america_customer_revenue` |
| Toyota revenue from customers in Europe | `toyota.europe_customer_revenue` |
| Toyota revenue from customers in Asia | `toyota.asia_customer_revenue` |
| Residual: Toyota revenue from customers elsewhere | `toyota.other_customer_revenue` |
| **Total: Toyota net revenue** | `toyota.net_revenue` |

A reconciling view: its parts are observed and reconciled against the total but carry nothing into it, so it can be imported alongside the driving view without counting a change twice.
Where customers are, not where the selling company is: Japanese companies' direct exports land in the destination. Overlaps the selling-company view of the same total.

#### reporting segments: segment revenue including inter-segment sales, IFRS (¥tn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Toyota automotive segment revenue | `toyota.automotive_revenue` |
| Toyota financial services revenue | `toyota.financial_services_revenue` |
| Residual: Toyota all other businesses revenue | `toyota.other_business_revenue` |
| Eliminations: Toyota inter-segment revenue eliminations | `toyota.segment_revenue_eliminations` |
| **Total: Toyota net revenue** | `toyota.net_revenue` |

A reconciling view: its parts are observed and reconciled against the total but carry nothing into it, so it can be imported alongside the driving view without counting a change twice.
Plan round: revenue by business, each segment with its inter-segment sales, and the eliminations that make them external. The third view of net revenue beside the selling-company (driving) and customer-location views; never added to them.

#### customer location: consolidated vehicle sales by region of sale (Toyota, Lexus, Daihatsu, Hino; excludes units retailed by equity-accounted JVs) (m units/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Toyota Japan vehicle volume | `toyota.japan_units` |
| Toyota North America vehicle volume | `toyota.north_america_units` |
| Toyota Europe vehicle volume | `toyota.europe_units` |
| Toyota Asia vehicle volume | `toyota.asia_units` |
| Residual: Toyota other regions vehicle volume | `toyota.other_regions_units` |
| **Total: Toyota consolidated vehicle volume** | `toyota.consolidated_units` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Where vehicles sell. US sales alone do not reveal tariff exposure: compare with where they are built.

#### production location: vehicle production by location of the plant (consolidated companies) (m units/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Toyota Japan production volume | `toyota.japan_production` |
| Toyota North America production volume | `toyota.north_america_production` |
| Toyota Europe production volume | `toyota.europe_production` |
| Toyota Asia production volume | `toyota.asia_production` |
| Residual: Toyota other regions production volume | `toyota.other_regions_production` |
| **Total: Toyota vehicle production volume** | `toyota.production_units` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Where vehicles are built. Japan builds far more than it sells (the export base); North America sells more than it builds (the import base). Not additive with the customer-location view.

### Identities

Each weight is derived from the values' levels and scales at construction (sd of the target per sd of the term), never estimated.

| Identity | Formula | Terms (weight, sd/sd) | Unit check |
|---|---|---|---|
| `ty.id.asia_revenue` (product) | Toyota Asia external revenue = Toyota Asia vehicle volume x Toyota Asia revenue per vehicle | Toyota Asia vehicle volume (factor, +1.000); Toyota Asia revenue per vehicle (factor, +0.800) | ¥tn/yr = m units/yr x ¥m/unit |
| `ty.id.cost_of_financing` (product) | Toyota cost of financing operations = 0.0166667 x Toyota financial services borrowings x Toyota finance subsidiaries funding cost | Toyota financial services borrowings (factor, +0.500); Toyota finance subsidiaries funding cost (factor, +0.889) | ¥tn/yr = ¥tn x % x 0.01 x 1.667 |
| `ty.id.dividends` (product) | Toyota cash dividends = 0.001 x Toyota dividend per share x Toyota shares outstanding | Toyota dividend per share (factor, +0.650); Toyota shares outstanding (factor, +0.239) | ¥tn/yr = ¥/share x bn shares x 0.001 |
| `ty.id.europe_revenue` (product) | Toyota Europe external revenue = Toyota Europe vehicle volume x Toyota Europe revenue per vehicle | Toyota Europe vehicle volume (factor, +0.833); Toyota Europe revenue per vehicle (factor, +0.667) | ¥tn/yr = m units/yr x ¥m/unit |
| `ty.id.fs_revenue` (product) | Toyota financial services revenue = 0.0160714 x Toyota finance receivables x Toyota retail finance contract rate | Toyota finance receivables (factor, +0.750); Toyota retail finance contract rate (factor, +1.071) | ¥tn/yr = ¥tn x % x 0.01 x 1.607 |
| `ty.id.industrial_fcf` (difference) | Toyota industrial free cash flow = Toyota non-financial-services operating cash flow - Toyota capital expenditure | Toyota non-financial-services operating cash flow (total, +1.000); Toyota capital expenditure (deduction, -0.307) | unknown |
| `ty.id.japan_exports` (difference) | Toyota Japan export volume = Toyota Japan production volume - Toyota Japan vehicle volume - Toyota Japan production neither sold in Japan nor exported | Toyota Japan production volume (total, +1.000); Toyota Japan vehicle volume (deduction, -0.500); Toyota Japan production neither sold in Japan nor exported (deduction, -0.312) | unknown |
| `ty.id.japan_revenue` (product) | Toyota Japan external revenue = Toyota Japan vehicle volume x Toyota Japan revenue per vehicle | Toyota Japan vehicle volume (factor, +0.800); Toyota Japan revenue per vehicle (factor, +0.800) | ¥tn/yr = m units/yr x ¥m/unit |
| `ty.id.na_imports` (difference) | Toyota North America import volume = Toyota North America vehicle volume - Toyota North America production volume | Toyota North America vehicle volume (total, +1.458); Toyota North America production volume (deduction, -1.042) | unknown |
| `ty.id.na_revenue` (product) | Toyota North America external revenue = Toyota North America vehicle volume x Toyota North America revenue per vehicle | Toyota North America vehicle volume (factor, +0.833); Toyota North America revenue per vehicle (factor, +0.667) | ¥tn/yr = m units/yr x ¥m/unit |

### Stocks and flows

A flow held one sd above its level adds its weight to the stock every period: the stock accumulates it.

| Stock-flow | Roll-forward | Flows (weight per period, sd/sd) |
|---|---|---|
| `ty.sf.shares` | Toyota shares outstanding (closing) = Toyota shares outstanding (opening) - Toyota shares repurchased, per 365 days | Toyota shares repurchased (outflow, -0.769) |

### Operating and financial paths

#### Competition from Chinese entrants (Southeast Asia)

**Trigger:** Chinese brands gaining share in Southeast Asia. **Endpoint:** Toyota operating profit.

Chinese brands share of Southeast Asian vehicle volume → Toyota Southeast Asia market share? → Toyota Asia vehicle volume? → Toyota Asia external revenue → Toyota Asia operating income? → Toyota operating profit  (? marks a step whose size is unknown)

Share loss reaches Asia operating income through volume; the incumbent's service network, parts and financing are the breaker; aftermarket and value-chain profit is an offset not represented as a value.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `ty_chinese_share` | Chinese brands' electric models gain share in Southeast Asia, largely from Japanese incumbents (Chinese automakers and Southeast Asian buyers) | EV price and range competitive; subsidies and fuel prices favor EVs; observable: market share by brand, EV penetration | onset ongoing; build years; persists structural; recognized Asia volumes | broker / broker / unknown / unknown | the incumbent's service network, parts logistics, financing and installed base hold share; local hybrid offers | Toyota Southeast Asia market share | unknown |
| 2 `ty_asia_share_units` | Share times market volume sets Toyota's Asia volume (customers) | market volume unchanged; observable: Toyota Asia volume | onset monthly; build none; persists with share; recognized units | inferred / inferred / unknown / unknown | market growth offsets share loss | Toyota Asia vehicle volume | unknown |
| 3 `ty_asia_units_rev` | Asia volume earns external revenue at Asia revenue per vehicle (Toyota Asia) | revenue per vehicle unchanged; observable: Asia external revenue | onset same quarter; build none; persists per unit; recognized revenue | documented / documented / unknown / documented | price cuts to defend share | Toyota Asia external revenue | +1.00 sd/sd (identity) |
| 4 `ty_asia_rev_oi` | Asia revenue contributes to Asia operating income at its contribution margin (Toyota Asia) | costs and mix as they are; observable: Asia segment results | onset same quarter; build none; persists while costs hold; recognized segment results | documented / documented / unknown / documented | price war; localization costs | Toyota Asia operating income | unknown |
| 5 `ty_reg_asia_oi` | Identity: Asia operating income adds to consolidated operating income (geographic view; never added to the business view) | same period, perimeter and accounting basis on both sides (operating income by geographic segment, location of the reporting company (IFRS, before eliminations)); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | consolidated operating income | +0.26 sd/sd (accounting) |

Unresolved inputs: Asia contribution margin (found not connected); Asia revenue per vehicle as a value (found connected); Southeast Asia share of Asia segment units (found not connected); Toyota share series by country (found not connected).

#### Cash and capital allocation

**Trigger:** a change in earnings. **Endpoint:** Toyota shares outstanding.

Toyota net income attributable to owners → [cash] Toyota non-financial-services operating cash flow? → [dividend_policy] Toyota dividend per share? → Toyota industrial free cash flow → Toyota industrial liquid assets? → Toyota cash dividends → Toyota industrial liquid assets? → Toyota shares repurchased? → Toyota shares outstanding → Toyota cash dividends  (? marks a step whose size is unknown)

Plan round: earnings → industrial operating cash → free cash flow after capex (identity) → liquid assets → capital actions: dividends (per share x shares, identity) and buybacks above the liquidity buffer under an open authorization → shares outstanding (stock-flow), which feeds back into the dividend bill. The finance book is funded by its own borrowings (ty_receivables_borrowings) and kept out of industrial cash. Authorized and completed buybacks are separate values (R8).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [cash] `ty_ni_ocf` | Earnings of the non-financial businesses turn into operating cash, after working capital, taxes paid and dividends received from affiliates (Toyota (treasury)) | working capital and tax timing as usual; the finance book's growth kept out (it is funded by its own debt); observable: the split cash flow statement (non-financial-services businesses) | onset same year; build quarters (working capital); persists persistent; recognized cash flow statement | documented / documented / unknown / inferred | working-capital swings; tax payments on prior years | Toyota non-financial-services operating cash flow | unknown |
| 2 [dividend_policy] `ty_ni_dps` | The board sets the dividend per share by its payout policy (a target payout ratio with stable or rising dividends) (Toyota board (capital policy)) | earnings above the level that would cut a stable dividend; observable: dividend notices; payout ratio | onset next dividend resolution; build a year; persists sticky (dividends rarely cut); recognized dividends declared | documented / documented / unknown / documented | a policy change; losses | Toyota dividend per share | unknown |
| 3 `ty_ocf_fcf` | Identity: industrial free cash flow is non-financial operating cash flow less capital expenditure | same period and perimeter (non-financial-services businesses); observable: the split cash flow statement | onset same period; build none; persists while the definition holds; recognized each fiscal year | documented / documented / documented / documented | capex measured on another perimeter (leased vehicles included) | Toyota industrial free cash flow | +1.00 sd/sd (identity) |
| 4 `ty_fcf_liquidity` | Free cash flow not paid out builds the industrial businesses' liquid assets (Toyota (treasury)) | no large acquisitions or investments in the year; observable: liquid assets at each period end | onset as earned; build the year; persists accumulates; recognized balance sheet | documented / documented / unknown / inferred | investments in affiliates, acquisitions, and securities purchases | Toyota industrial liquid assets | unknown |
| 5 `ty_dps_dividends` | Identity: total dividends are the dividend per share times shares outstanding | same fiscal year; shares outstanding at the period end stand in for the shares at each record date (approximation); observable: dividends declared; shares outstanding | onset same period; build none; persists while the definition holds; recognized each fiscal year | documented / documented / documented / documented | large buybacks between record dates | Toyota cash dividends | +0.65 sd/sd (identity) |
| 6 `ty_dividends_liquidity` | Dividends are paid from the industrial businesses' cash (Toyota (treasury)) | paid in cash; observable: cash flow statement; liquid assets | onset on payment; build none; persists accumulates; recognized cash flow statement | documented / documented / unknown / documented | none | Toyota industrial liquid assets | unknown |
| 7 `ty_liquidity_buyback` | Liquid assets above what management holds for resilience (a crisis buffer of months of costs) fund buybacks (Toyota board (capital policy)) | liquidity above the buffer (a threshold, not sized); an open authorization; observable: buyback resolutions; liquid assets | onset next resolution; build over the repurchase window; persists while above the buffer; recognized treasury stock | documented / inferred / unknown / inferred | investment needs (electrification, software), a rating constraint, or a large acquisition | Toyota shares repurchased | unknown |
| 8 `ty_buyback_shares` | Shares the company repurchases become treasury stock and leave the shares outstanding; retiring treasury shares later changes shares issued, not shares outstanding (Toyota (capital management)) | repurchases under a board resolution (a maximum number of shares and amount over a stated period); observable: monthly repurchase notices; shares issued and treasury stock at each period end | onset as purchased; build over the repurchase period; persists permanent unless reissued; recognized treasury stock at the period end | documented / documented / documented / documented | reissuance of treasury shares (the employee stock ownership trust's grants) | Toyota shares outstanding | -0.77 sd/sd (stock-flow, accumulates per 365 days) |
| 9 `ty_shares_dividends` | Identity: total dividends are the dividend per share times shares outstanding | same fiscal year; period-end shares as the approximation; observable: dividends declared; shares outstanding | onset same period; build none; persists while the definition holds; recognized each fiscal year | documented / documented / documented / documented | large buybacks between record dates | Toyota cash dividends | +0.24 sd/sd (identity) |

Unresolved inputs: cash conversion of segment profit (not disclosed in reviewed sources); liquidity buffer management holds (not disclosed in reviewed sources); payout ratio target (found not connected); shares reissued from treasury (not disclosed in reviewed sources).

#### Affiliates: China joint ventures

**Trigger:** Chinese demand for the joint ventures' vehicles. **Endpoint:** Toyota net income attributable to owners.

China real GDP growth → Toyota retail volume through equity-accounted affiliates? → [equity_income] Toyota share of equity-method income? → [retail_volume] Toyota group retail volume → Toyota income before income taxes → [no_group_tax] Toyota income tax expense → Toyota net income attributable to owners → Toyota net income attributable to owners  (? marks a step whose size is unknown)

JV unit growth raises retail volume and equity-method income, not consolidated revenue or operating income. s43 is the broad statistical summary (China growth to global retail volume) and is never added to it.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `ty_china_jv_units` | Faster Chinese growth lifts sales of the China joint ventures, which Toyota equity-accounts (Chinese buyers; JV partners) | the JVs hold share against domestic brands' price war; observable: China retail sales of the JVs | onset one to two quarters; build quarters; persists with the cycle; recognized JV results, then equity-method income | inferred / inferred / unknown / unknown | price war with domestic EV brands; JV reorganization (reported, not verified) | Toyota retail volume through equity-accounted affiliates | unknown |
| 2 [equity_income] `ty_jv_units_equity` | Units retailed by equity-accounted JVs reach Toyota's results only as its share of their profit, below operating income (JVs; accounting) | the JVs are profitable; ownership share unchanged; observable: share of profit of equity-method investees | onset JV reporting; build none; persists persistent; recognized below operating income, in the quarter | documented / documented / unknown / unknown | JV losses or impairment; ownership change (consolidation would move units into revenue) | Toyota share of equity-method income | unknown |
| 3 [retail_volume] `ty_retail_unconsolidated` | Identity (approximate): units retailed by equity-accounted affiliates (mostly the China JVs) add to group retail units but not to consolidated revenue | same period, perimeter and accounting basis on both sides (units); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | group retail units | +0.45 sd/sd (accounting) |
| 4 `ty_pretax_equity` | Identity: the share of equity-method investees' profit (already after their tax) adds to income before income taxes | same period, perimeter and accounting basis on both sides (consolidated income statement, IFRS); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | income before income taxes | +0.20 sd/sd (accounting) |
| 5 [no_group_tax] `ty_tax_equity_exclusion` | Equity-method income is already after the investees' tax, so it adds no group tax: this offsets the formula's charge on it (accounting) | IFRS presentation of share of profit after tax; observable: tax reconciliation | onset same period; build none; persists persistent; recognized income tax expense | model / model / documented / documented | dividend withholding taxes on remittances | Toyota income tax expense | -0.17 sd/sd |
| 6 `ty_ni_pretax` | Identity: income before income taxes is the start of net income | same period, perimeter and accounting basis on both sides (consolidated income statement, IFRS); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | net income attributable to owners | +1.25 sd/sd (accounting) |
| 7 `ty_ni_tax` | Identity: income tax expense is deducted | same period, perimeter and accounting basis on both sides (consolidated income statement, IFRS); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | net income attributable to owners | -0.38 sd/sd (accounting) |

Unresolved inputs: JV restructuring status and accounting (found connected); equity-method income by investee (found connected).

#### Execution and share

**Trigger:** a stronger or weaker new-model pipeline (launches, redesigns, quality). **Endpoint:** Toyota operating profit.

Toyota new-model pipeline → [north_america] Toyota North America market share? → [asia] Toyota Southeast Asia market share? → [investment] Toyota capital expenditure? → Toyota North America vehicle volume? → Toyota Asia vehicle volume? → Toyota North America external revenue → Toyota Asia external revenue → Toyota North America operating income? → Toyota Asia operating income? → Toyota operating profit → Toyota operating profit  (? marks a step whose size is unknown)

Competitive product retains or gains share and so regional earnings; the investment branch ends at capital expenditure (cash before earnings). Its depreciation lands in the business view (ty_capex_auto_oi) and is not added to these regional routes.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [north_america] `ty_pipeline_na_share` | New and redesigned models give buyers a competitive product, retaining or gaining share (Toyota product planning; customers) | launch on time, quality holds, supply ramps; observable: launch dates, share by segment, quality and recall data | onset launch; build a model cycle; persists until competitors' next cycle; recognized units and share | inferred / inferred / unknown / unknown | launch delays, recalls or certification problems; competitor launches | Toyota North America market share | unknown |
| 2 [asia] `ty_pipeline_asia_share` | Localized and electrified launches defend share against entrants in Southeast Asia (Toyota product planning) | competitive price and range; observable: launches, share | onset launch; build a model cycle; persists unknown; recognized units and share | broker / inferred / unknown / unknown | entrants' price cuts | Toyota Southeast Asia market share | unknown |
| 3 [investment] `ty_pipeline_capex` | Launches and localization need tooling and plant investment (cash before earnings) (Toyota) | programmes approved; observable: capital expenditure | onset ahead of launch; build a year or two; persists programme life; recognized cash flow when spent; depreciation after | inferred / inferred / unknown / unknown | programmes deferred | Toyota capital expenditure | unknown |
| 4 `ty_na_share_units` | Share times industry volume sets Toyota's North America volume (customers) | industry volume unchanged; observable: Toyota North America volume | onset monthly; build none; persists with share; recognized units | inferred / inferred / unknown / unknown | industry contraction | Toyota North America vehicle volume | unknown |
| 5 `ty_asia_share_units` | Share times market volume sets Toyota's Asia volume (customers) | market volume unchanged; observable: Toyota Asia volume | onset monthly; build none; persists with share; recognized units | inferred / inferred / unknown / unknown | market growth offsets share loss | Toyota Asia vehicle volume | unknown |
| 6 `ty_na_rev_units` | Identity: North America external revenue is units sold times revenue per vehicle (log terms add) | same period, perimeter and accounting basis on both sides (revenue per vehicle is defined as external revenue over units, so the identity is exact); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | toyota.north_america_external_revenue | +0.83 sd/sd (identity) |
| 7 `ty_asia_units_rev` | Asia volume earns external revenue at Asia revenue per vehicle (Toyota Asia) | revenue per vehicle unchanged; observable: Asia external revenue | onset same quarter; build none; persists per unit; recognized revenue | documented / documented / unknown / documented | price cuts to defend share | Toyota Asia external revenue | +1.00 sd/sd (identity) |
| 8 `ty_na_rev_to_oi` | Revenue contributes to regional operating income at the contribution margin after variable costs, with fixed-cost absorption on top (Toyota North America) | contribution costs, capacity and mix as they are; observable: segment revenue and operating income; the bridge's volume and mix line | onset same quarter; build none; persists while costs hold; recognized segment results | documented / documented / unknown / documented | cost inflation, mix-down, warranty or recall costs; inventory accumulation | Toyota North America operating income | unknown |
| 9 `ty_asia_rev_oi` | Asia revenue contributes to Asia operating income at its contribution margin (Toyota Asia) | costs and mix as they are; observable: Asia segment results | onset same quarter; build none; persists while costs hold; recognized segment results | documented / documented / unknown / documented | price war; localization costs | Toyota Asia operating income | unknown |
| 10 `ty_reg_north_america_oi` | Identity: North America operating income adds to consolidated operating income (geographic view; never added to the business view) | same period, perimeter and accounting basis on both sides (operating income by geographic segment, location of the reporting company (IFRS, before eliminations)); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | consolidated operating income | +0.55 sd/sd (accounting) |
| 11 `ty_reg_asia_oi` | Identity: Asia operating income adds to consolidated operating income (geographic view; never added to the business view) | same period, perimeter and accounting basis on both sides (operating income by geographic segment, location of the reporting company (IFRS, before eliminations)); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | consolidated operating income | +0.26 sd/sd (accounting) |

Unresolved inputs: Asia contribution margin (found not connected); Asia revenue per vehicle as a value (found connected); Southeast Asia share of Asia segment units (found not connected); contribution margin per vehicle (found not connected); industrial free cash flow (excluding financial-services receivable growth) (found not connected); launch calendar (not disclosed in reviewed sources); quality incidents (found not connected); transaction price per vehicle in North America (not disclosed in reviewed sources).

#### Financing: borrower conditions and credit losses

**Trigger:** US borrowers' income and employment weakening. **Endpoint:** Toyota operating profit.

US real GDP growth → Toyota finance credit loss rate? → Toyota financial services other expenses? → Toyota financial services operating income → Toyota operating profit?  (? marks a step whose size is unknown)

Plan round: borrower conditions → arrears and charge-offs → provisions in the segment's expenses → financial services operating income. The US finance subsidiary's provision is the observable (another basis, R14); the segment's provision line is not split. Lands in the business view, which reconciles to operating profit.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `ty_income_arrears` | Stronger borrower income lowers arrears and losses (borrowers) | employment and income follow growth; observable: delinquencies | onset quarters; build a year; persists credit cycle; recognized provisions | inferred / inferred / unknown / unknown | payment shock from rates | Toyota finance credit loss rate | unknown |
| 2 `ty_credit_loss_expense` | Higher credit losses raise provisions in the segment's expenses (Toyota finance subsidiaries) | expected-loss provisioning; observable: credit-loss provision | onset when expected losses rise; build quarters; persists credit cycle; recognized provisions in the quarter | inferred / inferred / unknown / unknown | recoveries on repossessed vehicles | Toyota financial services other expenses | unknown |
| 3 `ty_fs_other_expenses` | Identity: the segment's other expenses (SG&A, credit-loss provisions) are deducted | same period, perimeter and accounting basis on both sides (financial services segment (IFRS)); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | financial services operating income | -0.83 sd/sd (accounting) |
| 4 `ty_seg_financial_services_operating_income` | Identity: financial services segment operating income adds to consolidated operating income (business-segment view) | same period, perimeter and accounting basis on both sides (segment operating income by business (IFRS, before intersegment eliminations)); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | consolidated operating income | unknown (accounting) |

Unresolved inputs: credit-loss provision line in the financial services segment (found not connected).

#### Financing: used-vehicle values, residuals and credit

**Trigger:** a fall or rise in used-vehicle values. **Endpoint:** Toyota operating profit.

US used-vehicle value index → [residual] Toyota lease residual value losses? → [severity] Toyota finance credit loss rate? → Toyota cost of financing operations? → Toyota financial services other expenses? → Toyota financial services operating income → Toyota financial services operating income → Toyota operating profit?  (? marks a step whose size is unknown)

Used values set lease outcomes at maturity (residual gains or losses within cost of financing) and loss severity on repossessions. Borrower income (ty_income_arrears) is a second driver of credit losses.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [residual] `ty_used_residual` | Higher used-vehicle values mean returned lease vehicles sell above contract residuals, so residual losses fall (Toyota finance subsidiaries (remarketing)) | lease returns at maturity; residuals set when used values were different; observable: auction values, lease return rates | onset at lease maturity; build over the maturing cohort; persists cohort by cohort; recognized depreciation and impairment of lease vehicles | inferred / inferred / unknown / unknown | residuals already reset; hybrid battery replacement costs weigh on older hybrids' values | Toyota lease residual value losses | unknown |
| 2 [severity] `ty_used_severity` | Higher collateral values cut the loss on each repossessed vehicle (Toyota finance subsidiaries) | repossessions sold at auction; observable: recovery rates | onset at repossession; build quarters; persists credit cycle; recognized charge-offs | inferred / inferred / unknown / unknown | low repossession volumes | Toyota finance credit loss rate | unknown |
| 3 `ty_residual_cost` | Residual losses on operating-lease vehicles are recognized as depreciation and impairment within cost of financing (accounting) | operating leases on the balance sheet; observable: cost of financing operations | onset impairment review or sale; build none; persists per cohort; recognized cost of financing | inferred / inferred / unknown / unknown | none (accounting) | Toyota cost of financing operations | unknown |
| 4 `ty_credit_loss_expense` | Higher credit losses raise provisions in the segment's expenses (Toyota finance subsidiaries) | expected-loss provisioning; observable: credit-loss provision | onset when expected losses rise; build quarters; persists credit cycle; recognized provisions in the quarter | inferred / inferred / unknown / unknown | recoveries on repossessed vehicles | Toyota financial services other expenses | unknown |
| 5 `ty_fs_cost_of_financing` | Identity: cost of financing operations (funding interest, lease depreciation and residual impairment) is deducted | same period, perimeter and accounting basis on both sides (financial services segment (IFRS)); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | financial services operating income | -2.50 sd/sd (accounting) |
| 6 `ty_fs_other_expenses` | Identity: the segment's other expenses (SG&A, credit-loss provisions) are deducted | same period, perimeter and accounting basis on both sides (financial services segment (IFRS)); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | financial services operating income | -0.83 sd/sd (accounting) |
| 7 `ty_seg_financial_services_operating_income` | Identity: financial services segment operating income adds to consolidated operating income (business-segment view) | same period, perimeter and accounting basis on both sides (segment operating income by business (IFRS, before intersegment eliminations)); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | consolidated operating income | unknown (accounting) |

Unresolved inputs: credit-loss provision line in the financial services segment (found not connected); lease maturity profile (found not connected); residual assumptions (found not connected).

#### Financing: funding cost and contract repricing

**Trigger:** a rise in US short and medium-term yields. **Endpoint:** Toyota operating profit.

UST 2Y yield → Toyota finance subsidiaries funding cost? → [funding] Toyota cost of financing operations → [repricing] Toyota retail finance contract rate? → [yield] Toyota financial services revenue → [affordability] Toyota North America vehicle volume? → [arrears] Toyota finance credit loss rate? → Toyota finance receivables? → [earning_book] Toyota financial services revenue → [funding_need] Toyota financial services borrowings? → Toyota cost of financing operations → Toyota financial services other expenses? → Toyota financial services operating income → Toyota financial services operating income → Toyota financial services operating income → Toyota operating profit?  (? marks a step whose size is unknown)

Funding cost reaches interest expense as debt refinances; contract rates reprice as the book turns over, earning more but costing affordability and raising arrears. Receivables growth is funded by debt: consolidated debt rising with the finance book is not industrial stress.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `ty_ust_funding` | The finance subsidiaries borrow mostly in dollars across the short and medium curve, so their new funding cost follows US yields (Toyota finance subsidiaries (treasury)) | maturing debt refinanced at current rates; credit spread stable; observable: new issue yields, ABS spreads | onset as debt matures and new issues price; build over the debt's average life; persists while rates hold; recognized interest expense | inferred / inferred / unknown / unknown | spread tightening; hedged (swapped) fixed funding delays it | Toyota finance subsidiaries funding cost | unknown |
| 2 [funding] `ty_funding_cost` | Higher funding cost raises interest expense on the funded book (Toyota finance subsidiaries) | book repricing (floating or maturing debt); observable: cost of financing operations | onset with refinancing; build over debt life; persists persistent; recognized cost of financing | documented / documented / unknown / unknown | matched funding: assets reprice too | Toyota cost of financing operations | +0.89 sd/sd (identity) |
| 3 [repricing] `ty_funding_reprice` | New loan and lease contracts are priced off funding cost plus a spread (a repricing decision) (Toyota finance subsidiaries) | competitive rates from banks and captives allow it; observable: contract APRs | onset new contracts; build as the book turns over (years); persists contract term; recognized finance revenue over contracts | inferred / inferred / unknown / unknown | subvention holds customer rates down (cost moves to the sales company) | Toyota retail finance contract rate | unknown |
| 4 [yield] `ty_customer_rate_rev` | Higher contract rates raise interest income as the book turns over (Toyota finance subsidiaries) | contracts written at the new rate; observable: financing revenue | onset new contracts; build years; persists contract term; recognized financing revenue | documented / documented / unknown / unknown | volume falls | Toyota financial services revenue | +1.07 sd/sd (identity) |
| 5 [affordability] `ty_customer_rate_units` | Counter-path: higher loan and lease rates raise monthly payments and cost some vehicle sales (customers) | financed purchases; payment-sensitive buyers; observable: monthly payment, finance penetration, sales | onset weeks; build months; persists unknown; recognized units | inferred / inferred / unknown / unknown | subvention | Toyota North America vehicle volume | unknown |
| 6 [arrears] `ty_customer_rate_arrears` | Higher payments strain borrowers and raise arrears (borrowers) | weaker borrower income; observable: delinquencies, charge-offs | onset quarters; build a year; persists credit cycle; recognized provisions | inferred / inferred / unknown / unknown | tighter underwriting | Toyota finance credit loss rate | unknown |
| 7 `ty_units_receivables` | More financed sales add retail receivables and leased vehicles at the finance penetration rate (Toyota finance subsidiaries) | finance penetration stable; observable: receivables, new contract volume | onset origination; build years; persists contract term; recognized balance sheet | documented / inferred / unknown / unknown | cash or bank-financed purchases | Toyota finance receivables | unknown |
| 8 [earning_book] `ty_receivables_rev` | A larger earning book earns more financing revenue (Toyota finance subsidiaries) | yield on the book held; observable: financing revenue, receivables | onset as balances grow; build years; persists persistent; recognized financing revenue | documented / documented / unknown / unknown | yield compression | Toyota financial services revenue | +0.75 sd/sd (identity) |
| 9 [funding_need] `ty_receivables_borrowings` | Receivables growth is funded with debt: consolidated debt rises with the finance book, which is not industrial stress (Toyota finance subsidiaries (treasury)) | leverage of the finance book stable; observable: financial-services debt, receivables | onset with origination; build none; persists contract term; recognized balance sheet | documented / documented / unknown / unknown | equity or ABS deconsolidation | Toyota financial services borrowings | unknown |
| 10 `ty_borrowings_cost` | More borrowings carry more interest expense (Toyota finance subsidiaries) | funding rate as it is; observable: cost of financing operations | onset as drawn; build none; persists debt term; recognized cost of financing | documented / documented / unknown / unknown | none (arithmetic at a given rate) | Toyota cost of financing operations | +0.50 sd/sd (identity) |
| 11 `ty_credit_loss_expense` | Higher credit losses raise provisions in the segment's expenses (Toyota finance subsidiaries) | expected-loss provisioning; observable: credit-loss provision | onset when expected losses rise; build quarters; persists credit cycle; recognized provisions in the quarter | inferred / inferred / unknown / unknown | recoveries on repossessed vehicles | Toyota financial services other expenses | unknown |
| 12 `ty_fs_revenue` | Identity: financial-services revenue less its costs is the segment's operating income | same period, perimeter and accounting basis on both sides (financial services segment (IFRS)); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | financial services operating income | +2.50 sd/sd (accounting) |
| 13 `ty_fs_cost_of_financing` | Identity: cost of financing operations (funding interest, lease depreciation and residual impairment) is deducted | same period, perimeter and accounting basis on both sides (financial services segment (IFRS)); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | financial services operating income | -2.50 sd/sd (accounting) |
| 14 `ty_fs_other_expenses` | Identity: the segment's other expenses (SG&A, credit-loss provisions) are deducted | same period, perimeter and accounting basis on both sides (financial services segment (IFRS)); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | financial services operating income | -0.83 sd/sd (accounting) |
| 15 `ty_seg_financial_services_operating_income` | Identity: financial services segment operating income adds to consolidated operating income (business-segment view) | same period, perimeter and accounting basis on both sides (segment operating income by business (IFRS, before intersegment eliminations)); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | consolidated operating income | unknown (accounting) |

Unresolved inputs: credit-loss provision line in the financial services segment (found not connected); finance penetration rate (found not connected); funding mix, maturity ladder and hedging (found not connected).

#### Group bridge: operating income to net income

**Trigger:** a change in consolidated operating income. **Endpoint:** Toyota net income attributable to owners.

Toyota operating profit → Toyota income before income taxes → [tax] Toyota income tax expense → [minorities] Toyota income attributable to non-controlling interests? → [identity] Toyota net income attributable to owners → Toyota net income attributable to owners → Toyota net income attributable to owners  (? marks a step whose size is unknown)

Income before tax, tax at the documented effective rate (calibrated), minorities (uncalibrated) and the net-income identity. Equity-method income and finance and FX items join below operating income.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `ty_pretax_op` | Identity: operating income adds to income before income taxes | same period, perimeter and accounting basis on both sides (consolidated income statement, IFRS); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | income before income taxes | +0.54 sd/sd (accounting) |
| 2 [tax] `ty_tax_formula` | Income tax expense is the effective rate times income before tax (a formula, with the rate an estimate) (accounting) | effective rate stable; equity-method income excluded (see ty_tax_equity_exclusion); observable: effective tax rate | onset same period; build none; persists while the rate holds; recognized income tax expense | documented / documented / documented / documented | tax-rate changes; deferred tax adjustments; one-offs | Toyota income tax expense | +0.83 sd/sd |
| 3 [minorities] `ty_nci_share` | Minority shareholders of consolidated subsidiaries take their share of those subsidiaries' profit (accounting) | the change arises in subsidiaries with minority holders; observable: net income attributable to non-controlling interests | onset same period; build none; persists persistent; recognized net income | documented / documented / unknown / documented | the change arises in wholly-owned units | Toyota income attributable to non-controlling interests | unknown |
| 4 [identity] `ty_ni_pretax` | Identity: income before income taxes is the start of net income | same period, perimeter and accounting basis on both sides (consolidated income statement, IFRS); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | net income attributable to owners | +1.25 sd/sd (accounting) |
| 5 `ty_ni_tax` | Identity: income tax expense is deducted | same period, perimeter and accounting basis on both sides (consolidated income statement, IFRS); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | net income attributable to owners | -0.38 sd/sd (accounting) |
| 6 `ty_ni_nci` | Identity: the non-controlling shareholders' share of consolidated subsidiaries' profit is deducted | same period, perimeter and accounting basis on both sides (consolidated income statement, IFRS); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | net income attributable to owners | -0.10 sd/sd (accounting) |

Unresolved inputs: minority share by subsidiary (found not connected).

#### New initiatives: robotics and automation

**Trigger:** a commitment of resources to in-house robotics and factory automation. **Endpoint:** Toyota operating profit.

Toyota robotics and automation commitment → [development_cost] Toyota R&D expense? → [deployment] Toyota robots in productive use? → [equipment] Toyota capital expenditure? → [productivity] Toyota manufacturing cost savings? → [paid_external_use] Toyota all other businesses operating income? → Toyota automotive operating income? → Toyota automotive operating income? → Toyota automotive operating income? → Toyota operating profit? → Toyota operating profit?  (? marks a step whose size is unknown)

Announcement, commitment, validated deployment and measured economics are separate states. Development and deployment costs come first; savings only after validated deployment; external sales are optionality, kept apart from established earnings.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [development_cost] `ty_robotics_rd` | Committing to robotics and automation adds development cost before any benefit (Toyota) | the programme is funded (announcement is not commitment); observable: R&D expense, programme budgets | onset on commitment; build years; persists programme life; recognized R&D expense | broker / inferred / unknown / unknown | programme scaled back | Toyota R&D expense | unknown |
| 2 [deployment] `ty_robotics_deploy` | Commitment becomes validated deployment only when robots do productive work in plants (Toyota production engineering) | data, dexterity, reliability, safety and labor acceptance solved; observable: deployments doing value-added work (not pilots or announcements) | onset years; build years; persists unknown; recognized capex and R&D before; cost of sales after | broker / broker / unknown / broker | technical hurdles; component supply concentrated in China; social acceptance | Toyota robots in productive use | unknown |
| 3 [equipment] `ty_robotics_capex` | Deployment needs equipment spending (Toyota) | deployment proceeds; observable: capital expenditure | onset with deployment; build years; persists programme life; recognized cash flow; depreciation after | inferred / inferred / unknown / unknown | leasing or partner funding | Toyota capital expenditure | unknown |
| 4 [productivity] `ty_robots_savings` | Robots doing productive work lower unit labor and manufacturing cost (measured productivity) (Toyota plants) | robots match or beat human productivity at lower cost; observable: the bridge's cost-reduction line; plant productivity | onset after ramp; build years; persists unknown; recognized cost of sales | broker / assumption / unknown / unknown | robots' cost and reliability fall short; savings offset by deployment cost | Toyota manufacturing cost savings | unknown |
| 5 [paid_external_use] `ty_robots_external` | Optionality: proven robots could be sold or licensed outside Toyota (paid external use), kept apart from established earnings (Toyota) | a product others pay for; observable: external robot revenue | onset years; build unknown; persists unknown; recognized other businesses' results | assumption / assumption / unknown / unknown | no external customers; projected robot units are not earnings | Toyota all other businesses operating income | unknown |
| 6 `ty_savings_auto_oi` | Measured cost savings raise automotive operating income (Toyota) | savings not passed to customers; observable: automotive segment results; cost-reduction bridge line | onset same quarter; build none; persists persistent; recognized segment results | documented / documented / unknown / documented | price competition passes savings on | Toyota automotive operating income | unknown |
| 7 `ty_rd_auto_oi` | R&D is expensed (mostly) in the automotive segment (accounting) | development costs not capitalized; observable: R&D expense | onset as incurred; build none; persists while spent; recognized SG&A and cost of sales | documented / documented / unknown / documented | capitalization of development costs | Toyota automotive operating income | unknown |
| 8 `ty_capex_auto_oi` | Capital spending becomes depreciation, a cost of the automotive segment after assets enter service (Toyota) | assets in service; observable: depreciation expense | onset when assets enter service; build over useful life; persists years; recognized cost of sales and SG&A | documented / documented / unknown / documented | impairment or cancelled programmes change the schedule | Toyota automotive operating income | unknown |
| 9 `ty_seg_automotive_operating_income` | Identity: automotive segment operating income adds to consolidated operating income (business-segment view) | same period, perimeter and accounting basis on both sides (segment operating income by business (IFRS, before intersegment eliminations)); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | consolidated operating income | unknown (accounting) |
| 10 `ty_seg_other_business_operating_income` | Identity: all other businesses segment operating income adds to consolidated operating income (business-segment view) | same period, perimeter and accounting basis on both sides (segment operating income by business (IFRS, before intersegment eliminations)); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | consolidated operating income | unknown (accounting) |

Unresolved inputs: committed budget (not disclosed in reviewed sources); deployment schedule (found connected); depreciation by segment (found not connected); external revenue from robots (not disclosed in reviewed sources); savings per robot (not disclosed in reviewed sources); unit cost (not disclosed in reviewed sources).

#### Pricing competition (North America)

**Trigger:** competitors raising incentives. **Endpoint:** Toyota operating profit.

US industry incentive spend per vehicle → [match] Toyota North America incentive spend per vehicle? → [hold_price] Toyota North America vehicle volume? → [price] Toyota North America revenue per vehicle? → [volume] Toyota North America vehicle volume? → [subvention] Toyota financial services revenue? → Toyota North America dealer inventory? → Toyota North America incentive spend per vehicle? → Toyota North America external revenue → Toyota North America external revenue → Toyota North America operating income? → Toyota operating profit  (? marks a step whose size is unknown)

Competitive conditions (rivals' incentives) → Toyota and dealer response (match, hold price, subvented financing; dealers lift incentives when stock builds) → realized net price and retained or lost volume → North America revenue and operating income. Subvented financing moves part of the incentive into financial-services revenue; it is eliminated on consolidation, so it is counted once, as an incentive. Management's walk reports marketing efforts as one line (volume, mix, price and incentives); it is kept whole and never split without support (R14).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [match] `ty_industry_incentives_match` | When competitors raise incentives, Toyota and its dealers match part of them to retain volume (a pricing decision) (Toyota North America sales and dealers) | competitor offers on overlapping models; Toyota inventory available; observable: incentive data by maker | onset weeks; build months; persists while competitors discount; recognized revenue reductions when sold | broker / inferred / unknown / unknown | strong demand or short supply lets Toyota hold incentives low | Toyota North America incentive spend per vehicle | unknown |
| 2 [hold_price] `ty_industry_incentives_conquest` | Alternate branch: if Toyota holds price, competitors' discounts take some of its buyers (customers) | Toyota does not match; close substitutes; observable: share, retail sales | onset weeks; build months; persists unknown; recognized units | inferred / inferred / unknown / unknown | loyal, supply-constrained segments (hybrids with waiting lists) | Toyota North America vehicle volume | unknown |
| 3 [price] `ty_incentive_to_rpv` | Incentives reduce realized net price and so revenue per vehicle (Toyota North America) | incentives booked as revenue reductions; observable: revenue per vehicle; the bridge's marketing-efforts line | onset when sold; build none; persists per unit; recognized revenue | documented / documented / unknown / documented | none (an accounting reduction), but mix and FX also move revenue per vehicle | Toyota North America revenue per vehicle | unknown |
| 4 [volume] `ty_incentive_to_units` | Incentives retain or win buyers (customer response) (customers) | buyers price-sensitive; inventory available; observable: retail sales, share | onset weeks; build months; persists unknown; recognized units | inferred / inferred / unknown / unknown | inventory shortage; competitors escalate | Toyota North America vehicle volume | unknown |
| 5 [subvention] `ty_incentive_subvention` | Rate subvention (a below-market loan rate the sales company pays for) raises the finance segment's revenue as it lowers automotive revenue; on consolidation the transfer eliminates, so the incentive is counted once, at group level (Toyota sales company and finance subsidiary) | the incentive is offered as subvented financing; observable: subvented share of contracts; intersegment revenue | onset contract origination; build over contract life; persists contract term; recognized finance revenue over the contract | inferred / inferred / unknown / unknown | cash incentives instead of subvented rates | Toyota financial services revenue | unknown |
| 6 `ty_na_units_to_inventory` | Sales faster than supply draw dealer inventory down (dealers) | supply not adjusted; observable: days' supply | onset weeks; build months; persists until supply responds; recognized unit data | inferred / inferred / unknown / unknown | production response | Toyota North America dealer inventory | unknown |
| 7 `ty_dealer_stock_incentives` | When dealer stock rises above target days' supply, Toyota and its dealers raise incentives to move it (dealer response) (Toyota North America sales and its dealers) | dealer stock above target; competitors discounting; observable: dealer days' supply; incentive spend per unit; the US releases' inventory commentary | onset next incentive program; build a month or two; persists until stock normalizes; recognized revenue (incentives are deducted) | documented / inferred / unknown / inferred | supply-constrained models with order backlogs need no incentives | Toyota North America incentive spend per vehicle | unknown |
| 8 `ty_na_rev_price` | Identity: North America external revenue is revenue per vehicle times units sold (log terms add) | same period, perimeter and accounting basis on both sides (revenue per vehicle is defined as external revenue over units, so the identity is exact); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | toyota.north_america_external_revenue | +0.67 sd/sd (identity) |
| 9 `ty_na_rev_units` | Identity: North America external revenue is units sold times revenue per vehicle (log terms add) | same period, perimeter and accounting basis on both sides (revenue per vehicle is defined as external revenue over units, so the identity is exact); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | toyota.north_america_external_revenue | +0.83 sd/sd (identity) |
| 10 `ty_na_rev_to_oi` | Revenue contributes to regional operating income at the contribution margin after variable costs, with fixed-cost absorption on top (Toyota North America) | contribution costs, capacity and mix as they are; observable: segment revenue and operating income; the bridge's volume and mix line | onset same quarter; build none; persists while costs hold; recognized segment results | documented / documented / unknown / documented | cost inflation, mix-down, warranty or recall costs; inventory accumulation | Toyota North America operating income | unknown |
| 11 `ty_reg_north_america_oi` | Identity: North America operating income adds to consolidated operating income (geographic view; never added to the business view) | same period, perimeter and accounting basis on both sides (operating income by geographic segment, location of the reporting company (IFRS, before eliminations)); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | consolidated operating income | +0.55 sd/sd (accounting) |

Unresolved inputs: contribution margin per vehicle (found not connected); dealer days' supply (not disclosed in reviewed sources); intersegment amount by segment (found connected); subvented share of incentives (found not connected); transaction price per vehicle in North America (not disclosed in reviewed sources).

#### Product mix (powertrain)

**Trigger:** fuel prices changing the economics of fuel efficiency. **Endpoint:** Toyota operating profit.

Brent crude → [hybrid] Toyota hybrid retail volume? → [battery_electric] Toyota battery-electric retail volume? → [engine_only] Toyota ICE and other retail volume? → Toyota global vehicle sales → Toyota global vehicle sales → Toyota global vehicle sales → Toyota automotive segment revenue? → Toyota automotive segment revenue? → Toyota automotive segment revenue? → Toyota automotive operating income? → Toyota operating profit?  (? marks a step whose size is unknown)

Customer preference shifts the powertrain mix; much of the hybrid gain substitutes for engine-only units, so retail volume moves less than the mix. Units reach automotive revenue only when consolidated companies sell them; margins by powertrain are unknown. Stays in the business-segment view.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [hybrid] `ty_fuel_hybrid` | Higher fuel prices raise the value of fuel economy and shift buyers toward hybrids (customers) | hybrid supply (batteries, capacity) available; prices competitive; observable: hybrid retail units, order backlogs, fuel prices | onset months; build quarters; persists while fuel stays high; recognized units | inferred / inferred / unknown / unknown | battery or capacity constraints cap supply; high battery replacement costs and dealer service lock-in deter some buyers | Toyota hybrid retail volume | unknown |
| 2 [battery_electric] `ty_fuel_bev` | Higher fuel prices raise the appeal of battery-electric vehicles (customers) | charging infrastructure and price parity; observable: BEV retail units | onset months; build quarters; persists unknown; recognized units | broker / inferred / unknown / unknown | subsidy cuts; charging limits | Toyota battery-electric retail volume | unknown |
| 3 [engine_only] `ty_fuel_ice` | Mix shift: buyers switch from engine-only to electrified models, so part of the hybrid gain is substitution, not new volume (customers) | electrified alternatives available on the same model; observable: powertrain mix | onset months; build quarters; persists unknown; recognized units | inferred / inferred / unknown / unknown | supply limits on electrified versions | Toyota ICE and other retail volume | unknown |
| 4 `ty_pt_hybrid_retail_units` | Identity: hybrid retail units add to Toyota and Lexus retail units (powertrain view) | same period, perimeter and accounting basis on both sides (Toyota and Lexus retail units by powertrain (includes units retailed by equity-accounted JVs)); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | Toyota and Lexus retail units | +0.64 sd/sd (accounting) |
| 5 `ty_pt_battery_electric_retail_units` | Identity: battery-electric retail units add to Toyota and Lexus retail units (powertrain view) | same period, perimeter and accounting basis on both sides (Toyota and Lexus retail units by powertrain (includes units retailed by equity-accounted JVs)); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | Toyota and Lexus retail units | +0.15 sd/sd (accounting) |
| 6 `ty_pt_ice_and_other_retail_units` | Identity: engine-only and other retail units add to Toyota and Lexus retail units (powertrain view) | same period, perimeter and accounting basis on both sides (Toyota and Lexus retail units by powertrain (includes units retailed by equity-accounted JVs)); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | Toyota and Lexus retail units | +0.80 sd/sd (accounting) |
| 7 `ty_hybrid_rev` | Hybrid units sold by consolidated companies earn automotive revenue at their realized prices (Toyota) | the units are sold by consolidated companies (not JVs); observable: automotive revenue; the bridge's volume and mix line | onset when sold; build none; persists per unit; recognized automotive revenue | documented / documented / unknown / documented | units retailed by JVs reach equity-method income instead | Toyota automotive segment revenue | unknown |
| 8 `ty_bev_rev` | Battery-electric units sold by consolidated companies earn automotive revenue at their realized prices (Toyota) | the units are sold by consolidated companies (not JVs); observable: automotive revenue; the bridge's volume and mix line | onset when sold; build none; persists per unit; recognized automotive revenue | documented / documented / unknown / documented | units retailed by JVs reach equity-method income instead | Toyota automotive segment revenue | unknown |
| 9 `ty_ice_rev` | Engine-only units sold by consolidated companies earn automotive revenue at their realized prices (Toyota) | the units are sold by consolidated companies (not JVs); observable: automotive revenue; the bridge's volume and mix line | onset when sold; build none; persists per unit; recognized automotive revenue | documented / documented / unknown / documented | units retailed by JVs reach equity-method income instead | Toyota automotive segment revenue | unknown |
| 10 `ty_auto_rev_oi` | Automotive revenue contributes to automotive operating income at the contribution margin; an electrified sales share is not a measured hybrid profit (Toyota) | costs (materials, labor, warranty, development) as they are; observable: automotive segment results; bridge lines | onset same quarter; build none; persists while costs hold; recognized segment results | documented / documented / unknown / documented | material cost inflation, mix-down, recalls, expense growth | Toyota automotive operating income | unknown |
| 11 `ty_seg_automotive_operating_income` | Identity: automotive segment operating income adds to consolidated operating income (business-segment view) | same period, perimeter and accounting basis on both sides (segment operating income by business (IFRS, before intersegment eliminations)); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | consolidated operating income | unknown (accounting) |

Unresolved inputs: margin by powertrain or model (not disclosed in reviewed sources); revenue per unit by powertrain (not disclosed in reviewed sources); share of these units retailed by JVs (not disclosed in reviewed sources).

#### Production disruption and recovery (certification)

**Trigger:** a certification restriction on models built in Japan (dated events). **Endpoint:** Toyota operating profit.

Toyota production withheld by certification restrictions → [production] Toyota Japan production volume → [deliveries] Toyota Japan vehicle volume? → [recovery_costs] Toyota disruption recovery costs? → Toyota Japan operating income? → Toyota Japan export volume → Toyota Japan intersegment revenue? → Toyota Japan operating income? → Toyota Japan operating income → Toyota operating profit  (? marks a step whose size is unknown)

Plan round: certification restriction → available production (units withheld) → deliveries and plant utilization, and recovery costs → Japan operating income → group (geographic identity). Exports fall through the export identity. The dated events (halt, orders, staged restarts) and the production loss measured from monthly data are local; an event replays as a level of the shortfall over its dates.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [production] `ty_cert_production` | A certification restriction stops the affected models' production at Japanese plants until the regulator confirms compliance; each withheld unit is a unit not built (Toyota group makers in Japan and the regulator) | the affected models are built in Japan; restarts follow model-by-model confirmations; observable: monthly Japan production of the affected maker; restart notices | onset the halt date; build none (a stop); persists until each model's restart; recognized production of the month | documented / documented / documented / documented | staged restarts after confirmations; other plants cannot build the affected models | Toyota Japan production volume | -0.72 sd/sd |
| 2 [deliveries] `ty_cert_deliveries` | Shipments of the affected models stop too, so dealers deliver only from stock; Japan sales fall with a lag set by dealer stock (Toyota group makers and dealers in Japan) | the shipment halt covers stock already built; observable: Japan sales of the affected maker by month | onset the shipment halt; build weeks (dealer stock runs down); persists until shipments resume; recognized sales of the month | documented / documented / unknown / documented | dealer stock and shipments of unaffected models | Toyota Japan vehicle volume | unknown |
| 3 [recovery_costs] `ty_cert_recovery` | A restriction brings compensation to suppliers and dealers, re-testing and restart costs while plants stand idle (Toyota group makers in Japan) | costs recognized as incurred, often as one-time items; observable: one-time expense lines in the results walk; segment commentary | onset during the halt; build quarters; persists one-time; recognized expenses of the quarter | documented / inferred / unknown / inferred | costs borne by suppliers or recovered from insurance | Toyota disruption recovery costs | unknown |
| 4 `ty_japan_production_to_oi` | Lower utilization at Japanese plants spreads fixed costs over fewer units and lowers Japan operating income (operating leverage) (Toyota parent and group makers in Japan) | fixed costs not cut during the halt (labor kept, plants idle); observable: Japan segment margin; production by month | onset same quarter; build none; persists while utilization stays low; recognized segment results | documented / inferred / unknown / inferred | temporary cost cuts; overtime recovering lost output later | Toyota Japan operating income | unknown |
| 5 `ty_exports_japan_production` | Identity (approximate): Japan export volume is Japan production minus Japan sales; more Japanese output at given domestic sales means more exports | same period, perimeter and accounting basis on both sides (units, ignoring inventory change); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | toyota.japan_export_units | +1.00 sd/sd (identity) |
| 6 `ty_exports_to_intersegment` | Exported vehicles are sold to Toyota's overseas distribution subsidiaries: intersegment revenue of the Japan segment (Toyota parent) | exports go to consolidated subsidiaries (not third-party distributors); observable: Japan intersegment revenue | onset shipment; build none; persists per shipment; recognized Japan segment revenue on shipment | documented / documented / unknown / documented | exports to third-party distributors are external revenue instead | Toyota Japan intersegment revenue | unknown |
| 7 `ty_intersegment_to_japan_oi` | Export revenue from overseas subsidiaries contributes to Japan operating income (it is eliminated only at group level) (Toyota parent) | transfer prices above Japanese unit cost; observable: Japan segment revenue and operating income | onset same quarter; build none; persists while transfer prices hold; recognized segment results | documented / inferred / unknown / documented | transfer-price support to overseas subsidiaries; Japanese fixed costs at low utilization | Toyota Japan operating income | unknown |
| 8 `ty_recovery_costs_oi` | Recovery costs are expenses of the Japanese makers, so they lower Japan operating income one for one (Toyota group makers in Japan) | the affected makers report in the Japan geographic segment; observable: Japan segment results; one-time expense lines in the walk | onset as incurred; build none; persists one-time; recognized expenses of the quarter | documented / documented / model / documented | costs booked at overseas subsidiaries | Toyota Japan operating income | -0.25 sd/sd |
| 9 `ty_reg_japan_oi` | Identity: Japan operating income adds to consolidated operating income (geographic view; never added to the business view) | same period, perimeter and accounting basis on both sides (operating income by geographic segment, location of the reporting company (IFRS, before eliminations)); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | consolidated operating income | +0.74 sd/sd (accounting) |

Unresolved inputs: Japan vehicle exports and inventory change as reported (found connected); deliveries lost per unit withheld (not disclosed in reviewed sources); export margin per unit (not disclosed in reviewed sources); fixed-cost base of the Japanese plants (not disclosed in reviewed sources); recovery costs by event (not disclosed in reviewed sources).

#### Regional growth (North America)

**Trigger:** faster US growth lifting new-vehicle demand. **Endpoint:** Toyota operating profit.

US real GDP growth → US light-vehicle selling rate? → Toyota North America vehicle volume? → [revenue] Toyota North America external revenue → [production] Toyota North America production volume? → [inventory] Toyota North America dealer inventory? → [imports] Toyota North America import volume → Toyota North America vehicle volume? → Toyota North America operating income? → Toyota North America operating income? → Toyota operating profit  (? marks a step whose size is unknown)

Industry demand becomes Toyota orders and realized sales only with product available; sales pull production (utilization and absorption), draw down dealer stock (availability feedback) and pull imports (the tariff base). s42 is the broad statistical summary of this path and is never added to it.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `ty_us_gdp_industry` | Faster US growth (income, employment, credit availability) raises industry new-vehicle demand (US households and fleets) | affordability (prices and loan rates) does not offset income growth; observable: SAAR, order banks | onset one to two quarters; build quarters; persists with the cycle; recognized monthly sales data | inferred / inferred / unknown / unknown | high loan rates or prices; supply shortage | US light-vehicle selling rate | unknown |
| 2 `ty_industry_to_na_units` | Toyota's North America volume rises with industry volume at its share (dealer orders become realized sales) (Toyota dealers and customers) | product availability (dealer inventory) and stable share; observable: Toyota monthly US sales, days' supply | onset weeks; build months; persists with demand; recognized units sold | inferred / inferred / unknown / unknown | low inventory caps sales; share loss | Toyota North America vehicle volume | unknown |
| 3 [revenue] `ty_na_rev_units` | Identity: North America external revenue is units sold times revenue per vehicle (log terms add) | same period, perimeter and accounting basis on both sides (revenue per vehicle is defined as external revenue over units, so the identity is exact); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | toyota.north_america_external_revenue | +0.83 sd/sd (identity) |
| 4 [production] `ty_na_units_to_production` | Demand pulls North America production up to capacity (utilization) (Toyota production planning) | capacity headroom and parts supply; observable: production volumes, utilization | onset one production plan cycle; build quarters; persists unknown; recognized production | inferred / inferred / unknown / unknown | capacity or parts constraints; imports fill demand instead; in a supply shortage production is capacity-limited, not demand-pulled, so this link's sign does not carry a supply shock | Toyota North America production volume | unknown |
| 5 [inventory] `ty_na_units_to_inventory` | Sales faster than supply draw dealer inventory down (dealers) | supply not adjusted; observable: days' supply | onset weeks; build months; persists until supply responds; recognized unit data | inferred / inferred / unknown / unknown | production response | Toyota North America dealer inventory | unknown |
| 6 [imports] `ty_imports_na_units` | Identity (approximate): North America import volume is North America sales minus North America production | same period, perimeter and accounting basis on both sides (units, ignoring inventory change and exports out of the region); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | toyota.na_import_units | +1.46 sd/sd (identity) |
| 7 `ty_inventory_to_units` | Product availability: more stock on dealer lots lets more orders turn into sales (dealers and customers) | inventory is the binding constraint; observable: days' supply versus sales | onset weeks; build months; persists unknown; recognized units sold | inferred / inferred / unknown / unknown | inventory above normal: availability no longer binds | Toyota North America vehicle volume | unknown |
| 8 `ty_na_production_to_oi` | Higher utilization spreads plant fixed costs over more units (absorption) (Toyota North America plants) | production sold, not stocked; observable: production volumes, segment operating income | onset same quarter; build none; persists while utilization holds; recognized segment results (cost of sales) | inferred / inferred / unknown / unknown | inventory accumulation (absorbed cost reverses later); overtime and launch costs | Toyota North America operating income | unknown |
| 9 `ty_na_rev_to_oi` | Revenue contributes to regional operating income at the contribution margin after variable costs, with fixed-cost absorption on top (Toyota North America) | contribution costs, capacity and mix as they are; observable: segment revenue and operating income; the bridge's volume and mix line | onset same quarter; build none; persists while costs hold; recognized segment results | documented / documented / unknown / documented | cost inflation, mix-down, warranty or recall costs; inventory accumulation | Toyota North America operating income | unknown |
| 10 `ty_reg_north_america_oi` | Identity: North America operating income adds to consolidated operating income (geographic view; never added to the business view) | same period, perimeter and accounting basis on both sides (operating income by geographic segment, location of the reporting company (IFRS, before eliminations)); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | consolidated operating income | +0.55 sd/sd (accounting) |

Unresolved inputs: US share of North America segment units (found not connected); US-only sales and production (Canada and Mexico flows into the US are tariffed too) (found not connected); component exports from Japan to North American plants (not disclosed in reviewed sources); contribution margin per vehicle (found not connected); fixed-cost base of the North America plants (not disclosed in reviewed sources); transaction price per vehicle in North America (not disclosed in reviewed sources).

#### Product supply availability (electrified)

**Trigger:** electrified supply capacity changing (battery supply, plant allocation). **Endpoint:** Toyota operating profit.

Toyota hybrid and electrified supply capacity → Toyota hybrid retail volume? → Toyota global vehicle sales → Toyota automotive segment revenue? → Toyota automotive operating income? → Toyota operating profit?  (? marks a step whose size is unknown)

Plan round: customer choice is the product-mix path; this is the supply side. While orders exceed supply, deliveries follow capacity. Units reach automotive revenue; margins by powertrain are not disclosed, and a sales share is not a margin (R14). Lands in the business view, which reconciles to operating profit (no size reaches the total).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `ty_supply_hybrid` | When hybrid orders exceed what Toyota can build, deliveries follow supply, not demand (supply availability) (Toyota production planning and suppliers (batteries, electric drive units)) | orders above capacity (an order backlog); observable: order backlog commentary; hybrid share of sales; production by powertrain | onset as capacity is added; build quarters to years; persists durable once built; recognized retail units, then revenue | documented / inferred / unknown / unknown | demand falls below capacity: then supply no longer binds and demand drives deliveries | Toyota hybrid retail volume | unknown |
| 2 `ty_pt_hybrid_retail_units` | Identity: hybrid retail units add to Toyota and Lexus retail units (powertrain view) | same period, perimeter and accounting basis on both sides (Toyota and Lexus retail units by powertrain (includes units retailed by equity-accounted JVs)); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | Toyota and Lexus retail units | +0.64 sd/sd (accounting) |
| 3 `ty_hybrid_rev` | Hybrid units sold by consolidated companies earn automotive revenue at their realized prices (Toyota) | the units are sold by consolidated companies (not JVs); observable: automotive revenue; the bridge's volume and mix line | onset when sold; build none; persists per unit; recognized automotive revenue | documented / documented / unknown / documented | units retailed by JVs reach equity-method income instead | Toyota automotive segment revenue | unknown |
| 4 `ty_auto_rev_oi` | Automotive revenue contributes to automotive operating income at the contribution margin; an electrified sales share is not a measured hybrid profit (Toyota) | costs (materials, labor, warranty, development) as they are; observable: automotive segment results; bridge lines | onset same quarter; build none; persists while costs hold; recognized segment results | documented / documented / unknown / documented | material cost inflation, mix-down, recalls, expense growth | Toyota automotive operating income | unknown |
| 5 `ty_seg_automotive_operating_income` | Identity: automotive segment operating income adds to consolidated operating income (business-segment view) | same period, perimeter and accounting basis on both sides (segment operating income by business (IFRS, before intersegment eliminations)); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | consolidated operating income | unknown (accounting) |

Unresolved inputs: electrified production capacity and order backlog (not disclosed in reviewed sources); margin by powertrain or model (not disclosed in reviewed sources); revenue per unit by powertrain (not disclosed in reviewed sources); share of these units retailed by JVs (not disclosed in reviewed sources).

#### Tariffs and sourcing

**Trigger:** a change in the US tariff regime on imported vehicles and parts. **Endpoint:** Toyota operating profit.

US effective tariff rate on imported vehicles → Toyota US tariff cost → [reprice] Toyota North America list-price index? → [resource] Toyota North America production volume? → [absorb] Toyota North America operating income → [transfer_price] Toyota Japan operating income? → [incentives] Toyota North America incentive spend per vehicle? → Toyota North America revenue per vehicle? → Toyota North America vehicle volume? → [realized_price] Toyota North America revenue per vehicle? → [customer_response] Toyota North America vehicle volume? → Toyota North America import volume → Toyota US customs value of covered imports? → Toyota Japan export volume? → Toyota US customs value of covered imports? → Toyota US tariff cost? → Toyota North America dealer inventory? → Toyota North America operating income? → Toyota North America external revenue → Toyota North America external revenue → Toyota North America operating income? → Toyota Japan intersegment revenue? → Toyota Japan operating income? → Toyota operating profit → Toyota operating profit  (? marks a step whose size is unknown)

Operational (plan round). (1) Covered imports: the customs base is the declared value of covered vehicles and parts entering the US, fed by North America imports and US-bound exports from Japan, neither of which is the base itself (R14); the duty falls due at customs entry (ty_customs_base_cost). (2) Who bears it: the US importer of record, booked in North America (ty_tariff_absorb), unless transfer-price support moves part to Japan. (3) Management response, parallel branches: absorb, reprice, trim incentives, resource, transfer-price support. (4) Customers, dealers and production respond: realized price and lost volume, dealer stock, local production and plant absorption. (5) Regional accounts: North America and Japan operating income, reconciled to the group by the geographic identities. Localization feeds back into a smaller base. Sized: the rate to the cost (guidance) and absorption (model).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `ty_tariff_cost` | A higher effective US duty on covered vehicles and parts raises the customs cost of what Toyota imports into the US (US government (regime); Toyota's US importing subsidiary pays) | covered origin and content (rules of origin, USMCA content, exemptions and deals) and imported volume; observable: tariff schedules and deal terms; customs entries and duty records by origin | onset customs entry date of covered goods; build as inventory imported before the change sells through; persists while the regime holds; recognized cost of sales of the quarter the vehicles are sold | documented / documented / guidance / inferred | exemption or deal lowering the rate; changed sourcing or content; missing exposure data invalidates sizing | Toyota US tariff cost | +0.92 sd/sd |
| 2 [reprice] `ty_tariff_reprice` | Management passes part of the duty into US list prices (a pricing decision) (Toyota North America pricing) | pricing discretion: competitors also raise prices or are equally exposed; demand strong enough; observable: price notices, MSRP changes, competitor price actions | onset next model-year or price-reset cycle; build over one to two price cycles; persists unknown; recognized revenue when sold | inferred / inferred / unknown / unknown | competitors holding prices caps pass-through; a demand slowdown forces incentives instead | Toyota North America list-price index | unknown |
| 3 [resource] `ty_tariff_resource` | Management shifts production and sourcing into North America to shrink the dutiable base (a sourcing decision) (Toyota production planning and suppliers) | spare or buildable local capacity and qualified local suppliers; the regime expected to last; observable: production plans, plant investment announcements, local-content figures | onset quarters for re-allocation; years for new capacity; build years; persists durable once built; recognized production volumes, then costs | inferred / inferred / unknown / unknown | capacity limits; a sourcing plan supports intent, not completed relief; regime reversal strands the investment | Toyota North America production volume | unknown |
| 4 [absorb] `ty_tariff_absorb` | The duty not passed on is a cost of sales of the importing subsidiary and lowers North America operating income (Toyota North America) | the importer of record is the US subsidiary and the cost is not recovered by price or supplier sharing; observable: segment results commentary on tariff cost; the bridge's other/expenses lines | onset when tariffed inventory sells; build one inventory turn; persists while the regime holds; recognized quarter of sale | documented / documented / model / inferred | price pass-through, supplier sharing or transfer-price support moves the cost elsewhere | Toyota North America operating income | -3.33 sd/sd |
| 5 [transfer_price] `ty_tariff_transfer` | Counter-path: the parent may support the US subsidiary by lowering intersegment export prices, moving part of the duty into the Japan segment (Toyota parent (transfer pricing)) | a transfer-price adjustment within tax rules; observable: Japan intersegment revenue per exported unit; segment commentary | onset next transfer-price reset; build unknown; persists unknown; recognized segment results | assumption / inferred / unknown / unknown | transfer-pricing rules; no support given | Toyota Japan operating income | unknown |
| 6 [incentives] `ty_tariff_incentives` | Management recovers part of the duty by cutting dealer and customer incentives rather than list prices (a pricing decision) (Toyota North America sales and dealers) | competitors also face tariffs; dealer stock lean enough to hold volume with less support; observable: incentive spend per unit; dealer days' supply; the company's marketing-efforts walk line (one aggregate) | onset next incentive program; build months; persists unknown; recognized revenue (incentives are deducted from revenue) | inferred / inferred / unknown / unknown | a demand slowdown or competitor discounts force incentives back up | Toyota North America incentive spend per vehicle | unknown |
| 7 `ty_incentive_to_rpv` | Incentives reduce realized net price and so revenue per vehicle (Toyota North America) | incentives booked as revenue reductions; observable: revenue per vehicle; the bridge's marketing-efforts line | onset when sold; build none; persists per unit; recognized revenue | documented / documented / unknown / documented | none (an accounting reduction), but mix and FX also move revenue per vehicle | Toyota North America revenue per vehicle | unknown |
| 8 `ty_incentive_to_units` | Incentives retain or win buyers (customer response) (customers) | buyers price-sensitive; inventory available; observable: retail sales, share | onset weeks; build months; persists unknown; recognized units | inferred / inferred / unknown / unknown | inventory shortage; competitors escalate | Toyota North America vehicle volume | unknown |
| 9 [realized_price] `ty_list_to_rpv` | List-price increases raise realized revenue per vehicle unless incentives offset them (customers and dealers) | affordability and product availability; incentives not raised in step; observable: net transaction prices, incentive levels, dealer inventory | onset next retail cycle; build a model year; persists unknown; recognized revenue when sold | inferred / inferred / unknown / unknown | incentives raised to hold volume erase the price benefit | Toyota North America revenue per vehicle | unknown |
| 10 [customer_response] `ty_list_to_units` | Higher prices lose some buyers (customer response) (customers) | price-sensitive segments; competitors with lower prices or unexposed supply; observable: retail sales, order banks, dealer days' supply | onset sales and order cadence (weeks); build months; persists unknown; recognized units sold | inferred / inferred / unknown / unknown | supply-constrained models (order backlogs) lose little volume | Toyota North America vehicle volume | unknown |
| 11 `ty_imports_na_production` | Identity (approximate): each vehicle built in North America for the region is one fewer import | same period, perimeter and accounting basis on both sides (units, ignoring inventory change and exports out of the region); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | toyota.na_import_units | -1.04 sd/sd (identity) |
| 12 `ty_tariff_base` | More vehicles sold in North America but built outside it means a larger dutiable base (Toyota North America (importer of record)) | the imports are covered (origin) and enter the US rather than Canada or Mexico; observable: North America sales minus production; US import data by origin | onset customs entry; build with the import mix; persists while sourcing is unchanged; recognized cost of sales when sold | inferred / inferred / unknown / unknown | imports from origins exempted or under a deal; Canadian and Mexican flows not captured by this volume | Toyota US tariff cost | unknown |
| 13 `ty_na_prod_to_exports` | Counter-path: building more in North America replaces vehicles that were exported from Japan (Toyota production planning) | the localized models were previously exported from Japan; observable: Japan exports by destination; North America production by model | onset as production shifts; build years; persists durable; recognized Japan production and intersegment revenue | inferred / inferred / unknown / unknown | Japanese capacity redeployed to other export markets | Toyota Japan export volume | unknown |
| 14 `ty_exports_customs_base` | Vehicles exported from Japan to the US enter at a declared customs value set by the intercompany transfer price; they are part of the covered base (Toyota parent (exporter) and Toyota's US importer of record) | the destination is the US (not Canada, Mexico or other markets) and the vehicles are covered by the regime; observable: exports from Japan by destination (monthly); customs entries by origin | onset shipment and customs entry; build with the export mix; persists while sourcing holds; recognized customs entry; cost of sales when sold | documented / inferred / unknown / inferred | exports rerouted to other destinations; a deal exempting Japanese vehicles | Toyota US customs value of covered imports | unknown |
| 15 `ty_customs_base_cost` | The duty is the customs value of covered imports times the effective rate; Toyota's US importer of record owes it at customs entry and expenses it in cost of sales as the vehicles sell (Toyota's US importer of record (pays the duty)) | the importer of record is the US subsidiary; the duty is paid at entry, before the vehicle is sold; observable: duty records by entry; the company's tariff impact line in the operating-income walk | onset customs entry (duty payable); build one inventory turn (expensed as tariffed stock sells); persists while the regime holds; recognized cost of sales of the quarter of sale | documented / documented / unknown / documented | a lower rate or exemption by deal; refunds of duties found unlawful (a refund reverses part of the cost) | Toyota US tariff cost | unknown |
| 16 `ty_na_units_to_inventory` | Sales faster than supply draw dealer inventory down (dealers) | supply not adjusted; observable: days' supply | onset weeks; build months; persists until supply responds; recognized unit data | inferred / inferred / unknown / unknown | production response | Toyota North America dealer inventory | unknown |
| 17 `ty_na_production_to_oi` | Higher utilization spreads plant fixed costs over more units (absorption) (Toyota North America plants) | production sold, not stocked; observable: production volumes, segment operating income | onset same quarter; build none; persists while utilization holds; recognized segment results (cost of sales) | inferred / inferred / unknown / unknown | inventory accumulation (absorbed cost reverses later); overtime and launch costs | Toyota North America operating income | unknown |
| 18 `ty_na_rev_price` | Identity: North America external revenue is revenue per vehicle times units sold (log terms add) | same period, perimeter and accounting basis on both sides (revenue per vehicle is defined as external revenue over units, so the identity is exact); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | toyota.north_america_external_revenue | +0.67 sd/sd (identity) |
| 19 `ty_na_rev_units` | Identity: North America external revenue is units sold times revenue per vehicle (log terms add) | same period, perimeter and accounting basis on both sides (revenue per vehicle is defined as external revenue over units, so the identity is exact); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | toyota.north_america_external_revenue | +0.83 sd/sd (identity) |
| 20 `ty_na_rev_to_oi` | Revenue contributes to regional operating income at the contribution margin after variable costs, with fixed-cost absorption on top (Toyota North America) | contribution costs, capacity and mix as they are; observable: segment revenue and operating income; the bridge's volume and mix line | onset same quarter; build none; persists while costs hold; recognized segment results | documented / documented / unknown / documented | cost inflation, mix-down, warranty or recall costs; inventory accumulation | Toyota North America operating income | unknown |
| 21 `ty_exports_to_intersegment` | Exported vehicles are sold to Toyota's overseas distribution subsidiaries: intersegment revenue of the Japan segment (Toyota parent) | exports go to consolidated subsidiaries (not third-party distributors); observable: Japan intersegment revenue | onset shipment; build none; persists per shipment; recognized Japan segment revenue on shipment | documented / documented / unknown / documented | exports to third-party distributors are external revenue instead | Toyota Japan intersegment revenue | unknown |
| 22 `ty_intersegment_to_japan_oi` | Export revenue from overseas subsidiaries contributes to Japan operating income (it is eliminated only at group level) (Toyota parent) | transfer prices above Japanese unit cost; observable: Japan segment revenue and operating income | onset same quarter; build none; persists while transfer prices hold; recognized segment results | documented / inferred / unknown / documented | transfer-price support to overseas subsidiaries; Japanese fixed costs at low utilization | Toyota Japan operating income | unknown |
| 23 `ty_reg_north_america_oi` | Identity: North America operating income adds to consolidated operating income (geographic view; never added to the business view) | same period, perimeter and accounting basis on both sides (operating income by geographic segment, location of the reporting company (IFRS, before eliminations)); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | consolidated operating income | +0.55 sd/sd (accounting) |
| 24 `ty_reg_japan_oi` | Identity: Japan operating income adds to consolidated operating income (geographic view; never added to the business view) | same period, perimeter and accounting basis on both sides (operating income by geographic segment, location of the reporting company (IFRS, before eliminations)); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | consolidated operating income | +0.74 sd/sd (accounting) |

Unresolved inputs: US-only import volume by origin (not disclosed in reviewed sources); competitor exposure (not disclosed in reviewed sources); contribution margin per vehicle (found not connected); cost gap of local vs Japanese production (not disclosed in reviewed sources); covered imported volume by origin (not disclosed in reviewed sources); customs value per imported vehicle (not disclosed in reviewed sources); export margin per unit (not disclosed in reviewed sources); fixed-cost base of the North America plants (not disclosed in reviewed sources); incentive spend per unit by period (not disclosed in reviewed sources); local capacity headroom (not disclosed in reviewed sources); parts tariffs on US-built vehicles (not disclosed in reviewed sources); pass-through rate (found not connected); price elasticity by model (not disclosed in reviewed sources); share of Japan exports bound for North America (found not connected); transaction price per vehicle in North America (not disclosed in reviewed sources); transfer-price support from the Japan parent to the US importer (not disclosed in reviewed sources).

#### Yen: transaction, translation and imported inputs

**Trigger:** a move in USD/JPY. **Endpoint:** Toyota operating profit.

USD/JPY → [disclosed_total] Toyota operating profit → [transaction] Toyota Japan operating income → [translation] Toyota North America operating income? → [imported_inputs] Toyota Japan imported materials cost? → Toyota Japan operating income? → Toyota operating profit → Toyota operating profit  (? marks a step whose size is unknown)

Reconciles to the disclosed aggregate FX impact (plan round, local record per period): transactional = US dollar + euro + other currencies, exactly, in each of eight actual periods; total FX effect = transactional + translational. Pack round (R13): the transaction branch is sized from the company's US dollar transactional line (documented); m29 carries only the remainder of the total FX effect (translation, the euro, other currencies; inferred). Translation and imported inputs stay unsized branches inside that remainder, so no effect is counted twice. Below-operating-income FX gains are not represented.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [disclosed_total] `m29` | Aggregate yen effect: a weaker yen raises consolidated operating income, mostly through dollar-priced exports from Japan (transaction), plus translation of overseas profits, less dearer imported inputs (Toyota (exporter and consolidating parent)) | export volume from Japan as it is; overseas subsidiaries profitable; little hedging beyond the short term; observable: the results bridge's transactional and translational FX lines, period by period, against the change in the average rate | onset as rates apply to shipments and quarterly averages; build a quarter or two as hedges roll off; persists while the rate holds; recognized operating income of the quarter | documented / documented / inferred / inferred | localization of production shrinks the export base; North America losses reverse the translation part; hedging delays it | Toyota operating profit | +0.54 sd/sd |
| 2 [transaction] `ty_yen_transaction` | Transaction effect: dollar-priced exports from Japan bring in more yen against yen-denominated Japanese costs (Toyota parent (exporter)) | export volume from Japan; little hedging beyond the short term; observable: the bridge's transactional FX line; Japan exports | onset as rates apply to shipments; build a quarter or two (hedge roll-off); persists while the rate holds; recognized segment results | documented / documented / documented / documented | yen strength reverses it; localization shrinks export volume; hedges delay it | Toyota Japan operating income | +1.22 sd/sd |
| 3 [translation] `ty_yen_translation` | Translation effect: North American subsidiaries' dollar profits translate into more yen when the yen is weaker; the sign follows the sign of the region's profit (a loss translates into a larger yen loss) (accounting (translation)) | North America operating income positive; observable: the bridge's translational FX line | onset average rate of each quarter; build none; persists while the rate holds; recognized segment results | documented / documented / unknown / documented | North America loss-making (reverses the sign); other currencies move differently | Toyota North America operating income | unknown; sign as stated while Toyota North America operating income is above 0, reversed otherwise |
| 4 [imported_inputs] `ty_yen_imports` | A weaker yen raises the yen cost of dollar-priced materials, parts and energy bought by the Japan segment (Toyota purchasing and suppliers) | dollar-priced inputs not hedged; suppliers pass the cost on; observable: material cost commentary; the bridge's cost lines | onset one or two quarters (supplier contracts); build quarters; persists unknown; recognized cost of sales | inferred / inferred / unknown / unknown | commodity prices falling at the same time | Toyota Japan imported materials cost | unknown |
| 5 `ty_material_japan_oi` | Dearer imported inputs raise Japan cost of sales (an offset inside the yen effect) (Toyota parent) | not recovered in price; observable: Japan segment margin | onset as inventory turns; build a quarter; persists while costs hold; recognized segment results | inferred / inferred / unknown / unknown | supplier cost reduction efforts | Toyota Japan operating income | unknown |
| 6 `ty_reg_japan_oi` | Identity: Japan operating income adds to consolidated operating income (geographic view; never added to the business view) | same period, perimeter and accounting basis on both sides (operating income by geographic segment, location of the reporting company (IFRS, before eliminations)); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | consolidated operating income | +0.74 sd/sd (accounting) |
| 7 `ty_reg_north_america_oi` | Identity: North America operating income adds to consolidated operating income (geographic view; never added to the business view) | same period, perimeter and accounting basis on both sides (operating income by geographic segment, location of the reporting company (IFRS, before eliminations)); observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same period; build none; persists while the definition holds; recognized each reported quarter (cumulative from Q2 of a fiscal year in the workbook) | documented / documented / documented / documented | a change of segment definition, perimeter or accounting basis (the history breaks at the US GAAP to IFRS switch) | consolidated operating income | +0.55 sd/sd (accounting) |

Unresolved inputs: per-yen translation sensitivity (found not connected); sensitivity to currencies other than the dollar (found connected); split of the yen sensitivity by channel (found connected); transactional effect per yen (found connected); translation of other regions' profits (found not connected).

## Validation

`tests/scenario/test_construction_toyota.py` (loads sally_demo once, through the service app):

| Check | Test |
|---|---|
| No `validate_construction` problems for Toyota; the view reports none | `test_no_construction_problems_for_toyota` |
| The eleven compositions exist, with the reviewer's views; segments and regions carry residual and eliminations | `test_required_compositions_exist` |
| Every part of every additive view has an accounting link to its total with a sign; deductions weigh negative; synthetic levels add up | `test_additive_views_reconcile_by_accounting_links` |
| Overlapping views share no part; intersegment supply is not an external-customer part | `test_regional_and_business_views_never_share_a_part` |
| Customer and production location are separate; exports and imports are the difference identities | `test_customer_and_production_views_are_separate` |
| No product margins; every value states view and basis | `test_no_product_margin_values`, `test_every_new_value_states_its_view_and_basis` |
| The twelve paths exist; every step has a transition (mechanism, next state), every uncalibrated step a sign | `test_required_paths_exist` |
| Tariffs as five transitions with parallel management responses; the customs cost per point sized from guidance, every response unknown | `test_tariff_path_has_the_five_transitions` |
| Yen: aggregate calibrated, branches uncalibrated and landing in separate accounts | `test_yen_branches_are_separate_and_never_added_to_the_aggregate` |
| s44 re-routed and uncalibrated; no vehicle-sales-to-profit link remains | `test_s44_is_rerouted_and_uncalibrated` |
| m29, s42, s43 keep source, target and size, and gain transitions | `test_broad_links_keep_their_records_and_gain_transitions` |
| Finance-book debt is financial services; subvention counted once | `test_financing_debt_is_not_industrial` |
| Group bridge identities and the calibrated tax formula | `test_group_bridge_reconciles` |
| No calibrated route reaches a total through two views | `test_no_calibrated_route_reaches_a_total_through_two_views` |
| Generalization trace (below) | `test_generalization_trace_japan_production_stoppage` |
| Export (v4.1.4): financial bridge, Toyota business-construction paths, transitions and calibration in relationship properties | `test_new_objects_reach_the_export` |
| API: `/graph` on the new ids, `…/entities/toyota/construction` (json and markdown), `…/entities/toyota/traces` | `test_new_objects_reach_the_api` |
| Every material claim has a located citation; every cited id is a catalogued source; every baseline value is cited (local files; skipped where absent, as on CI) | `test_every_material_claim_resolves_to_a_located_citation` |
| No input `not_yet_reviewed`; `not_disclosed` lists what was searched, `found` where; only source ids are named | `test_no_input_is_left_unreviewed` |
| Every additive view adds up exactly at the model's medians | `test_compositions_reconcile_at_the_model_medians` |
| One driving view per total: regions drive operating profit, selling company drives net revenue; the other views reconcile without a size | `test_one_driving_view_per_total` |
| The eight identities exist, every term has an identity link with a derived weight, and they reconcile at the medians (and at the baselines, the financing products blocked for want of rates) | `test_identities_are_exact_and_reconcile`, `test_compositions_reconcile_at_the_local_baselines` |
| The translation effect's sign follows North America's profit | `test_translation_sign_follows_north_america_profit` |
| Pack round: the FY2025 baselines reconcile (money views), the rest blocked not flagged; financing identities blocked by the rate alone | `test_fy2025_baselines_reconcile` |
| Pack round: shares outstanding rolls forward between four dated counts with buybacks | `test_shares_roll_forward_between_dated_counts` |
| Plan round: the tariff path is operational (customs base, duty at entry, incentives branch, dealer and plant response; R14 notes) | `test_tariff_path_has_the_five_transitions` |
| Plan round: pricing has a dealer response; supply availability reaches mix; units are not margins | `test_pricing_and_mix_paths_are_operational` |
| Plan round: the yen channels reconcile to the disclosed FX impact per period (local) | `test_yen_channels_reconcile_to_the_disclosed_fx_impact` |
| Plan round: funding, borrower and used-value paths; the US subsidiary maps to its scope, never a composition part | `test_financial_services_paths_and_subsidiary_scope` |
| Plan round: certification restriction to production, deliveries, utilization and recovery costs; dated events | `test_production_disruption_path_uses_dated_events` |
| Plan round: eight standalone quarters, derived walk quarters, breaks, bindings with version and formula (R15) | `test_history_is_standalone_and_bindings_name_their_formula` |
| Plan round: cash and capital keeps finance funding and authorizations apart; dividend identity at both years | `test_cash_and_capital_path_keeps_finance_funding_and_authorizations_apart` |
| Plan round: the three validation cases through forecast, export and trace (R16) | `test_validation_tariff_absorption_versus_price_recovery`, `test_validation_financing_pressure`, `test_validation_outside_the_cases_north_american_plant_stoppage` |
| Every test runs in `sally_demo` and in the focused world `sally_focus` | module fixture |
| Every additive view adds up at the local baselines, totals included (skipped where absent) | `test_compositions_reconcile_at_the_local_baselines` |

Sally's expected-paths test (`tests/scenario/test_sally_expected_paths.py`) still passes: m29 keeps the
yen-to-Toyota-profit must channel with its sign. Since the pack round its size is the remainder after the transaction
branch, and the transaction branch adds a second calibrated route to her targets through the regional view.

**Generalization trace: a stoppage of Japanese production** (a supplier failure, an earthquake, a cyber incident; no
path was written for it). `trace(graph, "toyota.japan_production", "toyota")`:

- Reaches operating profit through the Japan export margin: Japan production → Japan export volume (identity) → Japan
  intersegment revenue → Japan operating income → operating profit (identity).
- Reaches operating profit through North American availability: Japan exports → North America dealer inventory →
  North America volume → external revenue (identity) and plant absorption → North America operating income →
  operating profit; and production volume by identity.
- Also reaches financial-services income through inventory → incentives → subvention (a segment-level transfer,
  eliminated at group level: a stop, not added to the regional routes) and the US duty base through lower imports.
- Where it stops: every route to profit rests on uncalibrated steps, so the model gives a direction and the
  conditions, not a size. It never reaches the automotive segment, equity-method income, the powertrain view, Europe
  or Asia: Japanese exports are linked only to North American supply, and component exports from Japan to overseas
  plants are not represented. The demand-pull link (North America volume → production) has the wrong regime in a
  supply shock; its breaker says so.
- Re-run Oct 18 against the second-round state: 35 routes, 13 ending at operating profit, each with an uncalibrated
  step; within six links, 4 routes reach operating profit and none is fully quantified (the coverage table above).
  Its inputs now say what was searched: reported exports from Japan are bound as a baseline, the destination split of
  exports and component exports to overseas plants are not disclosed in the reviewed sources.

## Completion report

Outcome codes map onto the project's release states: built and verified = in the model and the export as an
accounting identity or calibrated link; built but uncalibrated = exported as `represented_uncalibrated` (mechanism and
sign, no size; forecasts list it under `unquantified`); blocked by a named input or not built = absent from the model
and stated here.

| # | Outcome | What was done, or what blocks it |
|---|---|---|
| G01 | built and verified | `ty.comp.reporting_segments`; FY2026 actual baselines local |
| G02 | built and verified | `ty.comp.regional_operating_income`, `ty.comp.regional_external_revenue`, `toyota.japan_intersegment_revenue` |
| G03 | built and verified | units sold vs built, revenue by customer location, export and import identities. US-only import volume by origin: blocked by a named input (covered imports by origin; the brand-basis US series is not on the consolidated basis) |
| G04 | built and verified (units) | powertrain view; margin by powertrain blocked by a named input (not disclosed) |
| G05 | built but uncalibrated | composition verified; funding cost, contract rate, credit loss and residual links blocked by funding mix and maturity, credit and residual data; pack round: FS borrowings observed at two dates from the company's summaries; the rates are not disclosed on the consolidated basis (the US subsidiary's are recorded as proxies, not observed) |
| G06 | built but uncalibrated | retail bridge verified; JV profit and ownership, and the reported reorganization, blocked (JV financials; the cited report is not in the local folder) |
| G07 | built and verified | s44 re-routed (consolidated volume → automotive revenue), uncalibrated |
| G08 | built and verified | s42, s43 unchanged in size; transitions added |
| G09 | built and verified (pack round) | transaction branch sized from the company's own walks (documented) and m29 re-sized to the remainder (inferred), R13. Before: m29 calibrated aggregate with transition (its size now cited to the client's per-yen inference, support `model`); branches uncalibrated; the per-channel split is found and cited but would double count m29 if used to size the branches. Re-labelling m29's taxonomy class: not built (shared taxonomy file; needs its owner) |
| G10 | built but uncalibrated | five transitions plus feedback; the customs cost per point of the rate calibrated Oct 18 (R05); pack round: absorption sized one for one (graded model, regional split not disclosed); every other response blocked by customs base, covered content and origin, pass-through and elasticity |
| G11 | built but uncalibrated | incentive and transaction-price data; Toyota share series |
| G12 | built but uncalibrated | region-specific demand elasticities and dealer inventory data |
| G13 | built but uncalibrated | revenue and margin by powertrain |
| G14 | built but uncalibrated | as G05 |
| G15 | built but uncalibrated | launch and quality data; industrial free cash flow blocked (not separable from finance receivables in the workbook) |
| G16 | built but uncalibrated | deployment schedule, cost and measured savings (announcement only) |
| G17 | built and verified | identities and calibrated tax formula; minorities uncalibrated (by-subsidiary data) |
| G18 | built and verified | `sources.json` workbook dependencies (local) |
| G19 | built and verified | export test |
| G20 | built and verified | API test |
| G21 | not built | `api/service.py` `edge()` should report calibration and a null effect for uncalibrated links (another owner) |
| G22 | built and verified (simulation) | no calibrated double route (test); observations of parts of both views in one item or day are folded for one view only ([README](README.md#overlapping-views-at-import)); using both views at once still blocked by engine support for alternative views |
| G23 | built (in the client's local day bundles) | the volume guidance is now a revision of `toyota.consolidated_units`, the profit guidance a revision rather than a reported result, and the Southeast Asia note moves `toyota.asia_market_share` |
| G24 | built and verified | entity description |

Counts: 24 gaps — 16 missing construction (10 of them also missing calibration), 5 incorrect mapping, 1 export
omission, 2 retrieval omission. Outcomes: 12 built and verified, 10 built but uncalibrated, 2 not built (both outside
this build's files). The second round's gaps and outcomes are in [its own completion report](#completion-report-second-round).

**What a downstream agent can now trace or calculate.** Any change to tariffs, US demand, incentives, Chinese
entrants' share, fuel prices, USD/JPY, US yields, used-vehicle values, the launch pipeline, robotics commitment or
Chinese demand traced step by step to a named segment and to group operating income, then (by identity and the
calibrated tax formula) to pretax and net income, with each step's conditions, observable, timing, evidence and
breaker. Calculations it can make: the yen aggregate (m29), the accounting identities of every view, North America
revenue from units and revenue per vehicle, the export and import approximations, the tax and net-income bridge, and
(Oct 18) the US customs cost from a change in the tariff rate; dated FY2026 levels, totals included, are in the local
baselines, and each claim and baseline resolves to its passage in the local citations.

**What remains unsupported.** The size of every operating step (tariff pass-through and absorption, elasticities,
contribution margins, incentive response, funding and credit sensitivities, residual values, robotics economics);
margins by powertrain; JV-level profit; the use of the found yen split without counting the yen twice; industrial
free cash flow; US-only import exposure by origin. The second round's [inputs by status](#inputs-by-status) says, for
each, whether the material was searched and what it holds.

## Repair round (Oct 19)

The reviewer's repair instructions (Fixes 1 to 14 and the model checks). This page holds ids, formulas, and structure only; the
figures (dated observations, management passages, the subsidiary's lines) are in the local `repair.json` of the company's source
folder, built by a local script from the Q1 FY3/27 summary, deck and Q&A, the Q1 FY3/26 summary, and the US finance subsidiary's
10-Q. Retrieval and agent loading are the runtime owner's, not this build's; the reading set and the activation aliases below are
cheap conveniences, not a retrieval fix.

| Fix | What changed (ids) | How it is checked |
|---|---|---|
| 1 Reported against estimated | Each Toyota value in the evidence pack carries `reported` (period, unit, scope, availability date, source location) apart from `estimate` (mean, sd, prior, derivation with the imported items that touched it, model version). `observed` is true only with a dated reported observation; `reportable` keeps the old flag. `evidence_count` = distinct source documents among references and observations; `evidence_ref_count` = references; `link_evidence_items` keeps the old number. Pairs: `observation_estimate_pairs` (`PAIR_...`). | `context/earnings.attach_repair`; `test_earnings.py` |
| 2 Quarterly bridge | `ty.bridge.quarterly_earnings_q1_fy3_27` (each period's arithmetic and the year-on-year change by line), observations `OBS_TY_Q_...`, explanations `EVD_...`, the China measures `ty.china.q1_fy3_27` (inside operating income, and the equity-method line: different accounts), the operating-income walk. | arithmetic computed in the exporter; residuals are rounding and shown |
| 3 Reconciliation | One selected baseline (`BASELINE_TY_FY3_26`, the dated FY3/26 actuals) runs through both operating-profit views; `baseline_reconciliations` (`RECON_...`) hold before (model state) and after, the cause of each part's gap, and the explicit residual. Composition ids and roles unchanged. | `check.py --reconcile --baselines` |
| 4 US financing endpoint | `ty.comp.us_fin_contribution`: net financing margin + net lease margin + other revenues - expenses + GAAP to IFRS adjustment = `toyota.us_fin_operating_contribution`; `ty.id.fs_us_scope` now translates the contribution, not the margin. The scope view `ty.comp.fs_by_scope` stays reconciling: the US module is blocked from the group endpoint (counted once, never added to the revenue/cost view). | `financing_bridges` (`ty.fin.us_rate_to_group`) |
| 5 Group financing lines | `ty.id.fs_revenue` and `ty.id.cost_of_financing` (constant multiples) are replaced by `ty.id.fs_interest_income` and `ty.id.fs_funding_interest` (balance x rate x 0.01) with fixed assumed lines `toyota.fs_lease_other_revenue` and `toyota.fs_depreciation_other_costs`, summed by `ty.comp.fs_revenue_lines` and `ty.comp.fs_cost_lines`. The exposure by reset date is `model/rate_exposure.py`. | `test_rate_exposure.py` |
| 6 Input classes | `input_classification` (`CLASS_...`): reported, derived, externally estimated, assumed, with the outputs that depend on each assumption and the resolution class (reconnect existing data, targeted extraction, explicit assumption). `features.input_class` on new and key values. | `attach_repair` |
| 7 to 14 | Assumed values and identities for one instance each: `ty.id.hybrid_mix_op`; `ty.id.price_recovery_in_year`, `ty.id.cost_recognized_in_year`, `ty.id.pricing_net_op`; `ty.id.us_duty_avoided`; FX channel boundaries (`fx_boundaries`); stale notes corrected (dealer stock, liquidity roll-forward, China figures); the OP-to-share-price default is exported as an uncalibrated hypothesis. Fixtures with intermediate values: `model_checks` (MC1 to MC4, M07 to M10). Every temporary input has an `assumption_records` entry (`ASM_...`), never observed. | `model/period_math.py`, `test_period_math.py` |

Schema gaps recorded in the pack: the dated event instance, the minimum of three ceilings for a buyback, the regional x business split
(undisclosed, so unknown), and a refund/receivable/cash split for duty.

Retrieval-side conveniences (not a retrieval fix): the registry row's activation terms now start with the companies' names, aliases and
tickers (alphabetical order had pushed "Toyota" out of the first 24); an earnings-quality search scope; `reading/` files `41_` to `44_`
with START_HERE routing earnings, baseline, financing and input questions to them; unique macro `link_id`s.
