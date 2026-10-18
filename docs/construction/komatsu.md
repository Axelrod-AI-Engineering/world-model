# Komatsu: business construction

<!-- toc -->
**Contents**

- [Gap register](#gap-register)
- [Audit before modifying](#audit-before-modifying)
- [Definitions and bases](#definitions-and-bases)
- [Readable view](#readable-view)
  - [Business composition](#business-composition)
  - [Identities](#identities)
  - [Stocks and flows](#stocks-and-flows)
  - [Matrix `km.mx.cmu_sales`: km.comp.cmu_by_demand x km.comp.cmu_by_region (the rows drive the total; km.comp.cmu_by_region reconciles)](#matrix-kmmxcmusales-kmcompcmubydemand-x-kmcompcmubyregion-the-rows-drive-the-total-kmcompcmubyregion-reconciles)
  - [Operating and financial paths](#operating-and-financial-paths)
- [Validation](#validation)
- [Completion report](#completion-report)
  - [Conversion (Oct 18): one driving view per total, identities, stock-flows, a matrix, a threshold](#conversion-oct-18-one-driving-view-per-total-identities-stock-flows-a-matrix-a-threshold)
- [What the method could not express for an equipment maker](#what-the-method-could-not-express-for-an-equipment-maker)
<!-- /toc -->

The fourth build of the method, and the second industrial after [Toyota](toyota.md): a construction and mining
equipment maker whose economics are new machines sold through dealers in eight regions, a large parts and service
aftermarket that follows how hard the installed fleet works, a captive finance arm, and an industrial-machinery
business; driven by miners' capex and commodity prices, construction activity (the US above all), China, realized
prices against steel and tariff costs, dealer stock, and a disclosed yen sensitivity. The construction lives in
`data/worlds/sally_demo/construction/komatsu.yaml` (values, new market entities, links with their transitions, named
paths, compositions) plus light edits to the `komatsu` block of entities.yaml (description; `features` on three values)
and to m30, m31, m32, s45, s46 in interactions.yaml (transitions; m30 resized from the company's disclosed
sensitivity, the others keep their sizes). This page is structure only: object ids, bases, categories, tests. The
client-derived side (workbook cells, broker and expert passages, dated baselines) stays local under
`data/sally_data/construction/komatsu/` (`gap_evidence.md`, `sources.json`, `citations.json`, `baselines.json`,
`estimates.json`, `input_search.md`, `reconciliation.md`, `coverage.md`, and the readable view with levels and traces in
`view/`).

Source ids used in transitions (each resolves locally in `sources.json` to a file, and in `citations.json` to the cell
or the page and line with the passage): `km.wb` the company model workbook supplied for the canvas (segment, demand-type,
product, region and walk history; guidance; the company's disclosed currency sensitivities and tariff cost; its
builder's own elasticities and allocations, kept apart and never used as magnitude evidence); `km.r1`, `km.r2` broker
notes (a company update; a sector note with the profit sensitivities of mining equipment and US construction);
`km.r3` an algorithmic rating note; `km.r4` a broker note on the Indonesian distributor (unit sales, contractors'
production); `km.x1`, `km.x2` expert calls on the US rental and dealer channel (no names recorded); `km.peer` sector
dashboards; `km.pub` public business and accounting knowledge.

## Gap register

Written before the model was changed. "Internal" is the loaded sally_demo graph and its YAML; "export" is the v4.1.4
pack the reviewer inspected (036, state 432), where Komatsu appears as N_KOMATSU with six relationships (the share-price
default, m30 labelled FX translation, m31, m32, s45, s46) and PATH_KOMATSU_YEN_EXPORTERS (the shared parallel-exporter
path). Categories: **MC** missing construction, **CAL** missing calibration, **MAP** incorrect mapping, **EXP** export
omission, **RET** retrieval omission. Outcomes are in the [completion report](#completion-report).

| # | Gap (missing or incorrect structure) | Present now (internal / export) | Add or correct | Evidence or input needed | Conclusions affected | Test that shows it done | Cat. |
|---|---|---|---|---|---|---|---|
| G01 | Reporting segments: construction, mining and utility equipment (CM&U), Retail Finance, Industrial Machinery & Others, corporate and eliminations; sales and segment profit | Internal: `komatsu.operating_profit` only. Export: N_KOMATSU, operating profit | `km.comp.segment_sales` (to `komatsu.net_sales`), `km.comp.segment_profit` (to `komatsu.operating_profit`, corporate and eliminations closing it) | Segment sales and profit (`km.wb`) | Which business a shock lands in; finance vs equipment profit | `test_required_compositions_exist`, `test_composition_parts_have_fixed_weight_accounting_links` | MC |
| G02 | CM&U by demand type (construction, mining) and by product (new equipment, after-sales parts, after-sales service) | Internal: none | `km.comp.cmu_by_demand`, `km.comp.construction_by_product`, `km.comp.mining_by_product` | Demand-type and product sales (`km.wb`) | Aftermarket vs equipment; mining's higher margin | `test_required_compositions_exist` | MC |
| G03 | Sales by customer region (Japan, North America, Latin America, Europe and CIS, China, Asia, Oceania, Middle East and Africa), each split into construction and mining | Internal: none | `km.comp.cmu_by_region` and eight `km.comp.<region>_by_demand`; since Oct 18 the matrix `km.mx.cmu_sales` (demand type drives, regions reconcile) | Region x demand-type sales (`km.wb`); regional profit is not reported | Where demand comes from; what China or Indonesia is worth | `test_region_by_demand_type_is_one_matrix`, `test_one_view_drives_each_total` | MC |
| G04 | Mining: commodity prices -> miners' capex -> mining-equipment demand -> Komatsu deliveries -> profit; m31/m32 jump from oil and from a demand index straight to profit | Internal: m31, m32 (calibrated, no transition). Export: E67, E69 | `km.path.mining_capex`, `km.path.coal_contractors`; copper, gold, iron ore, thermal coal, mining capex values; broker drop-through on new equipment | Capex sensitivity to prices, lead times, Komatsu's share (not disclosed); the broker's equipment sensitivity (found) | Mining cycle conclusions | `test_required_paths_exist`, `test_mining_is_driven_through_products_and_construction_through_regions` | MC / CAL |
| G05 | Aftermarket: fleet hours -> parts and service -> margin mix | Internal: none | `komatsu.installed_fleet_hours`, `km.path.aftermarket` | Fleet hours, aftermarket margin (not disclosed) | "The aftermarket cushions a capex downturn" | `test_mining_is_driven_through_products_and_construction_through_regions` | MC / CAL |
| G06 | US construction: nonresidential and housing activity, long rates, the rental and dealer channel, dealer inventory | Internal: none | `us_construction` values, `komatsu.na_dealer_inventory`, `km.path.us_construction`, `km.path.us_rates`; broker drop-through on US construction | Demand elasticities, dealer stock series (not disclosed; expert view found) | North America growth vs profit; destocking risk | `test_dealer_destocking_is_a_stock_with_a_threshold`, `test_stock_flows_roll_forward` | MC / CAL |
| G07 | China construction as its own (small) regional route | Internal: s45, s46 only | `km.path.china_construction` | China excavator series (not obtained); China margin (not disclosed) | Sally's China-easing thesis for Komatsu | `test_required_paths_exist` | MC |
| G08 | Yen: m30 not tied to the company's disclosed per-yen sensitivity; labelled FX translation though mostly transaction; EUR and AUD sensitivities absent | Internal: m30 (0.3, no transition). Export: REL_KOMATSU__E70_FX_TRANSLATION | m30 resized from the disclosure (documented), with a transition; disclosed sales sensitivity and EUR/AUD links; transaction, translation, imported-input branches uncalibrated (`km.path.yen`); `aud_jpy.rate` | Channel split, hedging, CNY/IDR/BRL (not disclosed) | Yen-to-profit size and channels | `test_the_yen_sensitivity_is_the_disclosed_one`, `test_shared_driver_responses_are_parallel_branches` | MAP / CAL |
| G09 | m31 (oil -> mining demand) and m32 (mining demand -> profit) unscoped | Internal: calibrated, no transition | Keep ids and sizes (statistical records); transitions naming them reduced forms, never steps of the mining paths | none | Double counting with the mining paths | `test_reduced_forms_are_never_steps_of_their_structural_paths` | MAP |
| G10 | s45 (China property -> global construction demand) and s46 (construction demand -> profit) unscoped; China is a small share of Komatsu's sales | Internal: calibrated, no transition | Keep (Sally's channels); transitions with the scope stated in the breaker | none | The size of China's effect on Komatsu | `test_reduced_forms_are_never_steps_of_their_structural_paths` | MAP |
| G11 | Price realization and steel cost: reprice vs absorb, customer response | Internal: none | `komatsu.price_realization`, `komatsu.material_cost_index`, `steel.price`, `km.path.price_cost` | Pass-through rate, steel share of cost, price elasticity (not disclosed) | "Price covers cost inflation" | `test_shared_driver_responses_are_parallel_branches`, `test_price_cost_and_tariffs_keep_gross_effects_apart` | MC / CAL |
| G12 | US tariffs: regime -> customs cost -> reprice or absorb -> customer response -> segment profit | Internal: none | `us_industrial_tariffs.effective_rate`, `komatsu.us_tariff_cost`, `km.path.tariffs`; the gross cost calibrated as a cost line | Covered import value and origin (not disclosed); the disclosed tariff cost (found) | North America profit under tariffs | `test_price_cost_and_tariffs_keep_gross_effects_apart` | MC / CAL |
| G13 | Retail finance: funding cost, contract repricing, finance book and debt (debt rising with the book is not industrial stress) | Internal: none | RF values, `km.path.retail_finance_rates`, `km.path.finance_book` | Funding mix, pass-through, finance assets, credit losses (not disclosed); RF debt (found) | Rates on the finance arm; leverage reading | `test_finance_debt_is_not_industrial` | MC / CAL |
| G14 | Industrial machinery: semiconductor and manufacturing capex | Internal: none | `global_semiconductors.fab_equipment_spending`, `km.path.industrial_machinery` | Segment sensitivity (not disclosed) | Non-CM&U profit | `test_required_paths_exist` | MC / CAL |
| G15 | Fixed costs and Japanese wages | Internal: none | `komatsu.fixed_costs`, `km.path.fixed_costs` | Japan labour-cost base (not disclosed) | Operating leverage | `test_required_paths_exist` | MC / CAL |
| G16 | The company's CM&U profit walk (FX, volume and mix, price, material and variable cost, fixed cost, other) | Internal: none | `km.comp.cmu_profit_walk` (reconciling, `drives: false`); the delta a `difference` identity of this year's and last year's segment result; the price line a `product` identity | Walk history (`km.wb`) | Attribution of a profit change | `test_priors_reconcile_within_half_a_percent`, `test_retail_finance_is_a_nested_bridge_with_its_identities` | MC |
| G17 | Group bridge below operating income: non-operating items, tax, minorities, equity in earnings of affiliates, net income | Internal: none | `km.comp.pretax`, `km.comp.net_income`, tax calibrated from the effective rate, `km.path.group_bridge` | Income statement (`km.r1`, `km.r2`) | EPS from an operating change | `test_required_paths_exist` | MC |
| G18 | Workbook bindings: which rows are disclosures and which the builder's assumptions (elasticities, region allocations of consensus, drop-through outside the US, steel share, finance pass-through) | Internal: none | Local `sources.json` bindings and inspected dependencies; no transition cites a builder's assumption as magnitude evidence | Formula inspection (`km.wb`) | Any size taken from the workbook | `test_only_evidenced_links_carry_new_sizes` | MAP |
| G19 | The world lacks the drivers: metals and coal, mining capex, steel, US construction, US industrial tariffs, AUD/JPY, chip equipment | Internal: oil only | New entities (`copper`, `gold`, `iron_ore`, `thermal_coal`, `steel`, `global_mining`, `us_construction`, `us_industrial_tariffs`, `aud_jpy`, `global_semiconductors`), linked uncalibrated so no other company moves | Shared-name review at merge | Every Komatsu path's trigger | `test_required_paths_exist` | MC |
| G20 | Compositions, paths, transitions not in the inspected export | Export: not represented in the inspected export | Export carries them: `financial_bridge`, `business_construction` paths, transitions in relationship properties | none | Downstream agent context | `test_new_objects_reach_the_export` | EXP |
| G21 | New node ids not retrievable | Internal API: values not present | `/v1/world-models/sally_demo/graph`, `…/entities/komatsu/construction` and its traces serve them | none | Agent retrieval | `test_new_objects_reach_the_api` | RET |
| G22 | A results release reports the regional and demand-type views of CM&U sales on one day; the import guard folds one | Import: `intake/overlap.py` | Not built here (shared code) | Matrix compositions in the method | Importing a full set of actuals | listed as blocked | RET |
| G23 | Entity description frames Komatsu only as the yen and mining capex | Internal: `komatsu.description` | Describe the composition | none | Retrieval context | `test_values_name_their_basis` (values); description reviewed | MAP |
| G24 | Retail Finance revenue is a part of the segment sales view and of the finance profit identity | Method: a part may sit in one additive view | `km.comp.retail_finance` an additive nested bridge (since Oct 18; held non-additive before); revenue and interest expense `product` identities | Method support for a part in views of different totals | Finance profit reconciliation | `test_retail_finance_is_a_nested_bridge_with_its_identities` | MC |

## Audit before modifying

| Requirement or object | Class | Controlling object | Action |
|---|---|---|---|
| Identity, aliases, kind, sector, the share-price default and memberships (`komatsu`; S8 "Yen exporters") | Already owned | entities.yaml `komatsu`; superentity seeds | untouched |
| m30 yen -> operating profit (Sally's must channel) | Already owned -> Modify lightly | interactions.yaml m30 | transition added; size recalibrated from the company's disclosed sensitivity (sign unchanged) |
| m31, m32, s45, s46 (statistical records; s45 and s46 are Sally's China channels) | Already owned -> Modify lightly | interactions.yaml | transitions added (reduced forms, scope, unresolved inputs); ids, sizes and kernels kept |
| `operating_profit`, `mining_demand`, `construction_demand` definitions; the entity description | Modify lightly | entities.yaml `komatsu` block | `features.view/basis` added; description widened; ids and priors kept |
| PATH_KOMATSU_YEN_EXPORTERS (parallel exporter responses) | Do not touch | superentity S8 | Komatsu's own yen path added beside it |
| m30's interaction taxonomy class (exported as FX translation) | Modify lightly (not done: shared taxonomy) | `taxonomy/interactions.yaml` | recorded (G08) |
| Compositions, operating states, connected paths, financial mappings, macro drivers, bindings | Missing | construction/komatsu.yaml; local sources, citations, baselines | built |
| Shared macro links (m01-m18, s05-s07, s50-s54) and other companies' objects | Do not touch | interactions.yaml, entities.yaml | untouched; Komatsu paths start below them |
| Import overlap guard | Do not touch (shared code) | `src/axelrod_wm/intake/overlap.py` | finding reported (G22) |

## Definitions and bases

- **Basis.** US GAAP, consolidated, fiscal year ending March; sales are external sales; segment profit as reported;
  operating income is segment profit plus corporate items, eliminations and other operating income or expense.
- **Regions** are the customer's region. From FY3/27 the company restated its regions (countries moved from the Middle
  East to Europe; a construction-to-mining reclassification in Latin America): baselines use the restated basis.
  Europe is held with CIS, and the Middle East with Africa (eight regions; the company reports ten). Regional profit
  is not reported.
- **Costs and charges are negative values** (other finance costs, corporate items, other non-operating, tax,
  minorities) and add with a positive weight equal to their native sd over the total's. The one exception is retail
  finance interest expense, held positive (it is the product of debt and a rate) and deducted with a negative weight.
- **One view drives each total.** CM&U sales: demand type drives (`km.comp.cmu_by_demand`); the eight regions are the
  columns of the matrix `km.mx.cmu_sales` and reconcile. Construction sales: the regions drive
  (`km.comp.construction_by_region`, whose parts are the matrix cells); the product split is reconciling
  (`drives: false`). Mining sales: the product view drives (new equipment follows miners' capex, parts and service
  follow fleet hours); the regional split is reconciling. A reconciling view's accounting links carry no weight: it
  is observed and checked against its total, never adds into it, so no shock reaches a total twice.
- **The walk** (`km.comp.cmu_profit_walk`) is the company's y/y attribution of CM&U segment profit and reconciles to
  the segment result delta (`drives: false`). The delta is a `difference` identity (this year's segment result less
  last year's), and the price line a `product` identity (price realization x CM&U sales x 0.01). The paths land in the
  segment result itself.
- **Retail finance** profit is revenue plus costs (a nested bridge: revenue is also a part of the segment sales view).
  Revenue is a `product` identity of finance assets and the book rate; interest expense one of finance debt and the
  funding cost; other finance costs are the residual of the costs view. Finance assets are a stock: new contracts in,
  collections out.
- **Dealer inventory** in North America is a stock (shipments in, dealers' retail sales out). End demand reaches
  shipments through retail sales; the destocking link from inventory to shipments has a threshold state (it bites
  only above a normal stock level), and stays uncalibrated because neither side's size is observed.
- **Calibrated causal links** are the company's disclosed currency sensitivities (m30 and the sales, EUR and AUD links),
  the gross tariff cost, the effective tax rate, the price-realization drop-through (documented), and two broker
  sensitivities (mining new-equipment and US construction drop-through); plus the kept records m31, m32, s45, s46.
  Identity and stock-flow links carry weights derived from the levels. Every other causal step is uncalibrated:
  mechanism, sign, conditions, observable, timing, evidence by claim, breaker, unresolved inputs with their search
  status. Steps that look like a state-dependent response but have no observable side sizes (cost pass-through,
  the price response of volume, contract repricing) say so in their note.

## Readable view

Generated by `uv run python scripts/construction/check.py sally_demo --entities komatsu` from the loaded model (the same
objects the API serves at `/v1/world-models/sally_demo/entities/komatsu/construction`). A `?` marks a step whose size is unknown
(uncalibrated). Levels are left out here; the local copy adds them (`view/levels.md`).

137 links touch its values: 74 calibrated, 63 uncalibrated (represented, size unknown), 71 accounting, 8 identity, 4 stock-flow; 1 state-dependent; 136 carry a transition.

### Business composition

#### regions: Asia CM&U sales by demand type (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Komatsu Asia construction sales | `komatsu.asia_construction_sales` |
| Komatsu Asia mining sales | `komatsu.asia_mining_sales` |
| **Total: Komatsu Asia CM&U sales** | `komatsu.asia_cmu_sales` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Asia's construction and mining sales: one row of the region x demand-type matrix (km.mx.cmu_sales).

#### regions: China CM&U sales by demand type (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Komatsu China construction sales | `komatsu.china_construction_sales` |
| Komatsu China mining sales | `komatsu.china_mining_sales` |
| **Total: Komatsu China CM&U sales** | `komatsu.china_cmu_sales` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
China's construction and mining sales: one row of the region x demand-type matrix (km.mx.cmu_sales).

#### product: CM&U sales by demand type (construction, mining) (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Komatsu construction equipment business sales | `komatsu.construction_sales` |
| Komatsu mining equipment business sales | `komatsu.mining_sales` |
| **Total: Komatsu construction, mining and utility equipment sales** | `komatsu.cmu_sales` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An exact split. Mining earns about two-thirds of its sales in the aftermarket and carries the higher margin. Overlaps the regional view: never added to it.

#### regions: CM&U sales by customer region (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Komatsu Japan CM&U sales | `komatsu.japan_cmu_sales` |
| Komatsu North America CM&U sales | `komatsu.north_america_cmu_sales` |
| Komatsu Latin America CM&U sales | `komatsu.latin_america_cmu_sales` |
| Komatsu Europe and CIS CM&U sales | `komatsu.europe_cis_cmu_sales` |
| Komatsu China CM&U sales | `komatsu.china_cmu_sales` |
| Komatsu Asia CM&U sales | `komatsu.asia_cmu_sales` |
| Komatsu Oceania CM&U sales | `komatsu.oceania_cmu_sales` |
| Komatsu Middle East and Africa CM&U sales | `komatsu.middle_east_africa_cmu_sales` |
| **Total: Komatsu construction, mining and utility equipment sales** | `komatsu.cmu_sales` |

A reconciling view: its parts are observed and reconciled against the total but carry nothing into it, so it can be imported alongside the driving view without counting a change twice.
Eight regions (Europe with CIS, Middle East with Africa). Customer location; Komatsu does not report regional profit. The passive view of the matrix km.mx.cmu_sales: reconciles, never drives.

#### operating state: CM&U segment profit change by factor (the company's walk) (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Komatsu CM&U profit change: foreign exchange factor | `komatsu.walk_fx` |
| Komatsu CM&U profit change: volume and mix factor | `komatsu.walk_volume_mix` |
| Komatsu CM&U profit change: selling price factor | `komatsu.walk_price_factor` |
| Komatsu CM&U profit change: material and variable cost factor | `komatsu.walk_variable_cost` |
| Komatsu CM&U profit change: fixed cost factor | `komatsu.walk_fixed_cost` |
| Residual: Komatsu CM&U profit change: other factor | `komatsu.walk_other_factor` |
| **Total: Komatsu CM&U segment result delta** | `komatsu.cmu_result_delta` |

A reconciling view: its parts are observed and reconciled against the total but carry nothing into it, so it can be imported alongside the driving view without counting a change twice.
The company's y/y attribution of CM&U segment profit. Reconciling: the change itself is the difference identity km.id.cmu_result_delta (this year's segment profit less last year's), the price line is km.id.price_effect, and each other line is the observable of its mechanism.

#### product: construction sales by product (new equipment, after-sales parts, after-sales service) (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Komatsu construction new-equipment sales | `komatsu.construction_equipment_sales` |
| Komatsu construction parts sales | `komatsu.construction_parts_sales` |
| Komatsu construction after-sales service | `komatsu.construction_service_sales` |
| **Total: Komatsu construction equipment business sales** | `komatsu.construction_sales` |

A reconciling view: its parts are observed and reconciled against the total but carry nothing into it, so it can be imported alongside the driving view without counting a change twice.
Reconciling: construction drivers act on the regional cells (km.comp.construction_by_region). Aftermarket by region is not disclosed.

#### regions: construction sales by customer region (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Komatsu Japan construction sales | `komatsu.japan_construction_sales` |
| Komatsu North America construction sales | `komatsu.north_america_construction_sales` |
| Komatsu Latin America construction sales | `komatsu.latin_america_construction_sales` |
| Komatsu Europe and CIS construction sales | `komatsu.europe_cis_construction_sales` |
| Komatsu China construction sales | `komatsu.china_construction_sales` |
| Komatsu Asia construction sales | `komatsu.asia_construction_sales` |
| Komatsu Oceania construction sales | `komatsu.oceania_construction_sales` |
| Komatsu Middle East and Africa construction sales | `komatsu.middle_east_africa_construction_sales` |
| **Total: Komatsu construction equipment business sales** | `komatsu.construction_sales` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
The driving view of construction sales: regional construction drivers act on these cells.

#### regions: Europe and CIS CM&U sales by demand type (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Komatsu Europe and CIS construction sales | `komatsu.europe_cis_construction_sales` |
| Komatsu Europe and CIS mining sales | `komatsu.europe_cis_mining_sales` |
| **Total: Komatsu Europe and CIS CM&U sales** | `komatsu.europe_cis_cmu_sales` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Europe and CIS's construction and mining sales: one row of the region x demand-type matrix (km.mx.cmu_sales).

#### regions: Japan CM&U sales by demand type (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Komatsu Japan construction sales | `komatsu.japan_construction_sales` |
| Komatsu Japan mining sales | `komatsu.japan_mining_sales` |
| **Total: Komatsu Japan CM&U sales** | `komatsu.japan_cmu_sales` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Japan's construction and mining sales: one row of the region x demand-type matrix (km.mx.cmu_sales).

#### regions: Latin America CM&U sales by demand type (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Komatsu Latin America construction sales | `komatsu.latin_america_construction_sales` |
| Komatsu Latin America mining sales | `komatsu.latin_america_mining_sales` |
| **Total: Komatsu Latin America CM&U sales** | `komatsu.latin_america_cmu_sales` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Latin America's construction and mining sales: one row of the region x demand-type matrix (km.mx.cmu_sales).

#### regions: Middle East and Africa CM&U sales by demand type (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Komatsu Middle East and Africa construction sales | `komatsu.middle_east_africa_construction_sales` |
| Komatsu Middle East and Africa mining sales | `komatsu.middle_east_africa_mining_sales` |
| **Total: Komatsu Middle East and Africa CM&U sales** | `komatsu.middle_east_africa_cmu_sales` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Middle East and Africa's construction and mining sales: one row of the region x demand-type matrix (km.mx.cmu_sales).

#### product: mining sales by product (new equipment, after-sales parts, after-sales service) (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Komatsu mining new-equipment sales | `komatsu.mining_equipment_sales` |
| Komatsu mining parts sales | `komatsu.mining_parts_sales` |
| Komatsu mining after-sales service | `komatsu.mining_service_sales` |
| **Total: Komatsu mining equipment business sales** | `komatsu.mining_sales` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
The driven mining view: new equipment follows miners' capex (lagged); parts and service follow fleet hours (steadier).

#### regions: mining sales by customer region (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Komatsu Japan mining sales | `komatsu.japan_mining_sales` |
| Komatsu North America mining sales | `komatsu.north_america_mining_sales` |
| Komatsu Latin America mining sales | `komatsu.latin_america_mining_sales` |
| Komatsu Europe and CIS mining sales | `komatsu.europe_cis_mining_sales` |
| Komatsu China mining sales | `komatsu.china_mining_sales` |
| Komatsu Asia mining sales | `komatsu.asia_mining_sales` |
| Komatsu Oceania mining sales | `komatsu.oceania_mining_sales` |
| Komatsu Middle East and Africa mining sales | `komatsu.middle_east_africa_mining_sales` |
| **Total: Komatsu mining equipment business sales** | `komatsu.mining_sales` |

A reconciling view: its parts are observed and reconciled against the total but carry nothing into it, so it can be imported alongside the driving view without counting a change twice.
Reconciling: mining is driven through the product view (equipment follows capex, the aftermarket fleet hours).

#### reporting segments: net income: pretax income less taxes and minorities, plus equity in earnings of affiliates (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Komatsu income before income taxes | `komatsu.pretax_income` |
| Komatsu income taxes | `komatsu.income_tax` |
| Komatsu income attributable to non-controlling interests | `komatsu.noncontrolling_interests` |
| Residual: Komatsu equity-method and other income | `komatsu.equity_method_income` |
| **Total: Komatsu net income attributable to owners** | `komatsu.owners_net_income` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Taxes and minorities are negative values. The residual is equity in earnings of affiliates and other items, and absorbs differences between sources.

#### regions: North America CM&U sales by demand type (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Komatsu North America construction sales | `komatsu.north_america_construction_sales` |
| Komatsu North America mining sales | `komatsu.north_america_mining_sales` |
| **Total: Komatsu North America CM&U sales** | `komatsu.north_america_cmu_sales` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
North America's construction and mining sales: one row of the region x demand-type matrix (km.mx.cmu_sales).

#### regions: Oceania CM&U sales by demand type (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Komatsu Oceania construction sales | `komatsu.oceania_construction_sales` |
| Komatsu Oceania mining sales | `komatsu.oceania_mining_sales` |
| **Total: Komatsu Oceania CM&U sales** | `komatsu.oceania_cmu_sales` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Oceania's construction and mining sales: one row of the region x demand-type matrix (km.mx.cmu_sales).

#### reporting segments: pretax income: operating income plus non-operating items (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Komatsu operating profit | `komatsu.operating_profit` |
| Residual: Komatsu other non-operating income and expense | `komatsu.other_nonoperating` |
| **Total: Komatsu income before income taxes** | `komatsu.pretax_income` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Net interest and other non-operating items are the residual.

#### financial services: Retail Finance segment: revenue less funding, credit and other costs (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Komatsu retail finance revenue | `komatsu.rf_revenue` |
| Komatsu retail finance costs | `komatsu.rf_costs` |
| **Total: Komatsu retail finance segment result** | `komatsu.rf_segment_result` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
A nested bridge: revenue is also a part of the segment sales view (a different total). Costs are revenue less segment profit, held negative.

#### financial services: Retail Finance costs: interest expense (a deduction) and other costs (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Komatsu retail finance interest expense | `komatsu.rf_interest_expense` |
| Residual: Komatsu retail finance other costs | `komatsu.rf_other_costs` |
| **Total: Komatsu retail finance costs** | `komatsu.rf_costs` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Interest expense is held positive and deducted; credit costs and expenses are the residual (negative).

#### reporting segments: operating income by segment: segment profit plus corporate, eliminations and other operating items (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Komatsu CM&U segment result | `komatsu.cmu_segment_result` |
| Komatsu retail finance segment result | `komatsu.rf_segment_result` |
| Komatsu industrial machinery and others segment result | `komatsu.imo_segment_result` |
| Eliminations: Komatsu corporate, eliminations and other operating items | `komatsu.corporate_eliminations` |
| **Total: Komatsu operating profit** | `komatsu.operating_profit` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
The view a business mechanism lands in. Corporate items, eliminations and other operating income or expense close it.

#### reporting segments: net sales by segment, external customers, US GAAP (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| Komatsu construction, mining and utility equipment sales | `komatsu.cmu_sales` |
| Komatsu retail finance revenue | `komatsu.rf_revenue` |
| Komatsu industrial machinery and others sales | `komatsu.imo_sales` |
| **Total: Komatsu net sales** | `komatsu.net_sales` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
External sales by segment add exactly to net sales (intersegment sales excluded, so no eliminations line).

### Identities

Each weight is derived from the values' levels and scales at construction (sd of the target per sd of the term), never estimated.

| Identity | Formula | Terms (weight, sd/sd) | Unit check |
|---|---|---|---|
| `km.id.cmu_result_delta` (difference) | Komatsu CM&U segment result delta = Komatsu CM&U segment result - Komatsu CM&U prior-year segment result | Komatsu CM&U segment result (total, +0.833); Komatsu CM&U prior-year segment result (deduction, -0.833) | unknown |
| `km.id.price_effect` (product) | Komatsu CM&U profit change: selling price factor = 0.01 x Komatsu CM&U selling-price realization x Komatsu construction, mining and utility equipment sales | Komatsu CM&U selling-price realization (factor, +1.950); Komatsu construction, mining and utility equipment sales (factor, +0.195) | ¥bn/yr y/y = pct y/y x ¥bn/yr x 0.01 |
| `km.id.rf_interest` (product) | Komatsu retail finance interest expense = 0.01 x Komatsu retail finance interest-bearing debt x Komatsu retail finance funding cost | Komatsu retail finance interest-bearing debt (factor, +0.750); Komatsu retail finance funding cost (factor, +1.250) | ¥bn/yr = ¥bn x pct x 0.01 |
| `km.id.rf_revenue` (product) | Komatsu retail finance revenue = 0.01 x Komatsu retail finance assets x Komatsu retail finance book rate | Komatsu retail finance assets (factor, +0.625); Komatsu retail finance book rate (factor, +0.909) | ¥bn/yr = ¥bn x pct x 0.01 |

### Stocks and flows

A flow held one sd above its level adds its weight to the stock every period: the stock accumulates it.

| Stock-flow | Roll-forward | Flows (weight per period, sd/sd) |
|---|---|---|
| `km.sf.dealer_inventory` | Komatsu North America dealer inventory (closing) = Komatsu North America dealer inventory (opening) + Komatsu North America construction sales - Komatsu North America dealer retail sales, per 365 days | Komatsu North America construction sales (inflow, +2.233); Komatsu North America dealer retail sales (outflow, -2.233) |
| `km.sf.rf_assets` | Komatsu retail finance assets (closing) = Komatsu retail finance assets (opening) + Komatsu retail finance new contracts - Komatsu retail finance collections, per 365 days | Komatsu retail finance new contracts (inflow, +1.055); Komatsu retail finance collections (outflow, -0.659) |

### Matrix `km.mx.cmu_sales`: km.comp.cmu_by_demand x km.comp.cmu_by_region (the rows drive the total; km.comp.cmu_by_region reconciles)

| | Komatsu Asia CM&U sales | Komatsu China CM&U sales | Komatsu Europe and CIS CM&U sales | Komatsu Japan CM&U sales | Komatsu Latin America CM&U sales | Komatsu Middle East and Africa CM&U sales | Komatsu North America CM&U sales | Komatsu Oceania CM&U sales |
|---|---|---|---|---|---|---|---|---|
| Komatsu construction equipment business sales | `komatsu.asia_construction_sales` | `komatsu.china_construction_sales` | `komatsu.europe_cis_construction_sales` | `komatsu.japan_construction_sales` | `komatsu.latin_america_construction_sales` | `komatsu.middle_east_africa_construction_sales` | `komatsu.north_america_construction_sales` | `komatsu.oceania_construction_sales` |
| Komatsu mining equipment business sales | `komatsu.asia_mining_sales` | `komatsu.china_mining_sales` | `komatsu.europe_cis_mining_sales` | `komatsu.japan_mining_sales` | `komatsu.latin_america_mining_sales` | `komatsu.middle_east_africa_mining_sales` | `komatsu.north_america_mining_sales` | `komatsu.oceania_mining_sales` |

Region x demand type. Demand type drives CM&U sales (mining through the product view, construction through the regional cells); regions reconcile.

### Operating and financial paths

#### Installed fleet, parts and service (mix)

**Trigger:** the installed mining fleet works more hours. **Endpoint:** Komatsu operating profit.

Komatsu installed mining fleet operating hours → [parts] Komatsu mining parts sales? → [service] Komatsu mining after-sales service? → [parts_revenue] Komatsu mining equipment business sales → [parts_margin] Komatsu CM&U segment result? → [service_revenue] Komatsu mining equipment business sales → [service_margin] Komatsu CM&U segment result? → Komatsu construction, mining and utility equipment sales → Komatsu net sales → Komatsu operating profit  (? marks a step whose size is unknown)

Utilization drives the aftermarket; more aftermarket in the mix raises the segment margin. Revenue lands in the mining product view, profit in segment profit.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [parts] `km-c-hours-miningparts` | More operating hours wear machines faster, so mines buy more parts (wear parts, components); the aftermarket follows utilization, not new-equipment orders (mine operators (Komatsu service network)) | machines under Komatsu service and parts supply; observable: mining after-sales sales in the results | onset 1-2 quarters; build quarters; persists with utilization; recognized net sales | broker / inferred / unknown / unknown | parts deferred by cash-strapped miners; competition from non-genuine parts | Komatsu mining parts sales | unknown |
| 2 [service] `km-c-hours-miningservice` | More operating hours wear machines faster, so mines buy more service (maintenance, rebuilds); the aftermarket follows utilization, not new-equipment orders (mine operators (Komatsu service network)) | machines under Komatsu service and parts supply; observable: mining after-sales sales in the results | onset 1-2 quarters; build quarters; persists with utilization; recognized net sales | broker / inferred / unknown / unknown | parts deferred by cash-strapped miners; competition from non-genuine parts | Komatsu mining after-sales service | unknown |
| 3 [parts_revenue] `km-a-minprod-parts` | Identity: Komatsu mining parts sales is one part of Komatsu mining equipment business sales (mining sales by product (new equipment, after-sales parts, after-sales service)); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu mining equipment business sales | +0.32 sd/sd (accounting) |
| 4 [parts_margin] `km-c-minparts-profit` | Mining after-sales parts add segment profit; aftermarket carries a higher margin than new machines, so more aftermarket in the mix raises the segment margin (Komatsu (CM&U)) | aftermarket pricing holds; observable: the walk's volume and mix line | onset same quarter; build none; persists per unit; recognized segment profit | broker / inferred / unknown / inferred | non-genuine parts competition; service contracts priced below cost to win equipment orders | CM&U segment profit | unknown |
| 5 [service_revenue] `km-a-minprod-service` | Identity: Komatsu mining after-sales service is one part of Komatsu mining equipment business sales (mining sales by product (new equipment, after-sales parts, after-sales service)); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu mining equipment business sales | +0.23 sd/sd (accounting) |
| 6 [service_margin] `km-c-minservice-profit` | Mining after-sales service add segment profit; aftermarket carries a higher margin than new machines, so more aftermarket in the mix raises the segment margin (Komatsu (CM&U)) | aftermarket pricing holds; observable: the walk's volume and mix line | onset same quarter; build none; persists per unit; recognized segment profit | broker / inferred / unknown / inferred | non-genuine parts competition; service contracts priced below cost to win equipment orders | CM&U segment profit | unknown |
| 7 `km-a-cmudem-mining` | Identity: Komatsu mining equipment business sales is one part of Komatsu construction, mining and utility equipment sales (CM&U sales by demand type (construction, mining)); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu construction, mining and utility equipment sales | +0.68 sd/sd (accounting) |
| 8 `km-a-sales-cmu` | Identity: Komatsu construction, mining and utility equipment sales is one part of Komatsu net sales (net sales by segment, external customers, US GAAP); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu net sales | +0.92 sd/sd (accounting) |
| 9 `km-a-op-cmu` | Identity: Komatsu CM&U segment result is one part of Komatsu operating profit (operating income by segment: segment profit plus corporate, eliminations and other operating items); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu operating profit | +1.04 sd/sd (accounting) |

Unresolved inputs: after-sales sales by region (not disclosed in reviewed sources); aftermarket margin versus new-equipment margin (not disclosed in reviewed sources); operating hours of Komatsu's installed mining fleet (not disclosed in reviewed sources).

#### China property and construction

**Trigger:** China's property market stabilizes. **Endpoint:** Komatsu operating profit.

China property sales → Komatsu China construction sales? → [revenue] Komatsu construction equipment business sales → [profit] Komatsu CM&U segment result? → Komatsu construction, mining and utility equipment sales → Komatsu operating profit  (? marks a step whose size is unknown)

China is a small market for Komatsu now (a few percent of CM&U sales). s45 and s46 (property to the global construction-demand index to operating profit) are the reduced form, never added to this path.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `km-c-property-chinacon` | A recovering property market restarts construction and lifts excavator demand in China; Komatsu sells at its (small) share (Chinese contractors) | Komatsu holds share against Chinese makers; observable: excavator sales in China | onset 1-2 quarters; build quarters; persists with starts; recognized net sales | assumption / inferred / unknown / unknown | Chinese makers' price competition holds Komatsu's share down; local-government funding limits | Komatsu China construction sales | unknown |
| 2 [revenue] `km-a-conreg-china` | Identity: Komatsu China construction sales is one part of Komatsu construction equipment business sales (construction sales by customer region); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu construction equipment business sales | +0.07 sd/sd (accounting) |
| 3 [profit] `km-c-chinacon-profit` | China construction sales contribute segment profit at a contribution margin squeezed by local price competition (Komatsu China) | prices hold; observable: the walk's volume and mix line | onset same quarter; build none; persists per unit; recognized segment profit | inferred / inferred / unknown / unknown | price war with Chinese makers | CM&U segment profit | unknown |
| 4 `km-a-cmudem-construction` | Identity: Komatsu construction equipment business sales is one part of Komatsu construction, mining and utility equipment sales (CM&U sales by demand type (construction, mining)); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu construction, mining and utility equipment sales | +0.61 sd/sd (accounting) |
| 5 `km-a-op-cmu` | Identity: Komatsu CM&U segment result is one part of Komatsu operating profit (operating income by segment: segment profit plus corporate, eliminations and other operating items); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu operating profit | +1.04 sd/sd (accounting) |

Unresolved inputs: China excavator sales (not disclosed in reviewed sources); drop-through of construction sales outside the US (not disclosed in reviewed sources); profitability of China construction sales (not disclosed in reviewed sources).

#### Thermal coal and mining contractors (Indonesia, Australia)

**Trigger:** thermal-coal prices rise. **Endpoint:** Komatsu operating profit.

Thermal coal price → [fleet_purchases] Mining industry capital expenditure? → [overburden] Komatsu installed mining fleet operating hours? → Mining equipment demand? → Komatsu mining new-equipment sales? → [parts] Komatsu mining parts sales? → [service] Komatsu mining after-sales service? → Komatsu CM&U segment result → Komatsu CM&U segment result? → Komatsu CM&U segment result? → Komatsu operating profit  (? marks a step whose size is unknown)

Coal contractors buy fleets when coal earns more, and run them harder (overburden removal). The Asia mining leaf is the regional observable; the profit route runs through the product view only, so the region and product views are never both driven.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [fleet_purchases] `km-c-coal-capex` | Higher thermal-coal prices raise coal miners' and contractors' cash flow, so contractors add and replace trucks and excavators (coal miners and mining contractors (Indonesia, Australia)) | prices expected to persist; balance sheets and permits allow expansion; observable: miners' capex guidance; commodity price curve | onset 2-4 quarters; build 1-2 years; persists with the commodity cycle; recognized miners' capex, then equipment orders | broker / broker / unknown / unknown | price spikes seen as temporary; miners' capital discipline (returns to shareholders first); permitting delays | mining industry capex | unknown |
| 2 [overburden] `km-c-coal-hours` | Higher coal prices raise contractors' coal production and overburden removal, so the installed fleet works more hours (mine operators and contractors) | mines not capacity- or weather-constrained; observable: production and overburden data; Komatsu telematics hours | onset 1-2 quarters; build quarters; persists with production; recognized parts and service demand | broker / inferred / unknown / unknown | transport bottlenecks (river barges), weather and quotas cap production; mine closures | installed mining fleet hours | unknown |
| 3 `km-c-capex-miningdemand` | Mining capex buys fleets: more capex means more orders for ultra-class trucks, shovels and loaders across the industry (mining companies (buyers)) | fleet purchases are part of the capex plan; observable: industry mining-equipment demand (company outlook, units y/y) | onset 1-2 quarters after approval; build a year; persists with capex; recognized orders and deliveries | broker / broker / unknown / unknown | capex spent on processing plants and infrastructure rather than fleets; leasing of fleets | industry mining equipment demand | unknown |
| 4 `km-c-miningdemand-equipment` | Industry mining-equipment demand becomes Komatsu new-equipment sales at its share, when machines are delivered (long lead times) (Komatsu mining sales (and distributors)) | share and production slots hold; observable: mining new-equipment sales in the results | onset at delivery; build quarters (lead times); persists with demand; recognized net sales when delivered | broker / broker / unknown / unknown | lost share; delivery slots or component shortages; order cancellations | Komatsu mining new-equipment sales | unknown |
| 5 [parts] `km-c-hours-miningparts` | More operating hours wear machines faster, so mines buy more parts (wear parts, components); the aftermarket follows utilization, not new-equipment orders (mine operators (Komatsu service network)) | machines under Komatsu service and parts supply; observable: mining after-sales sales in the results | onset 1-2 quarters; build quarters; persists with utilization; recognized net sales | broker / inferred / unknown / unknown | parts deferred by cash-strapped miners; competition from non-genuine parts | Komatsu mining parts sales | unknown |
| 6 [service] `km-c-hours-miningservice` | More operating hours wear machines faster, so mines buy more service (maintenance, rebuilds); the aftermarket follows utilization, not new-equipment orders (mine operators (Komatsu service network)) | machines under Komatsu service and parts supply; observable: mining after-sales sales in the results | onset 1-2 quarters; build quarters; persists with utilization; recognized net sales | broker / inferred / unknown / unknown | parts deferred by cash-strapped miners; competition from non-genuine parts | Komatsu mining after-sales service | unknown |
| 7 `km-c-mineq-profit` | Incremental mining new-equipment sales add segment profit at their drop-through (contribution margin after variable cost) (Komatsu (CM&U)) | fixed costs and prices as they are; observable: the walk's volume and mix line | onset same quarter; build none; persists per unit; recognized segment profit | broker / broker / broker / inferred | mix of machines; price concessions in a weak market; fixed-cost absorption changes with volume | CM&U segment profit | +0.38 sd/sd |
| 8 `km-c-minparts-profit` | Mining after-sales parts add segment profit; aftermarket carries a higher margin than new machines, so more aftermarket in the mix raises the segment margin (Komatsu (CM&U)) | aftermarket pricing holds; observable: the walk's volume and mix line | onset same quarter; build none; persists per unit; recognized segment profit | broker / inferred / unknown / inferred | non-genuine parts competition; service contracts priced below cost to win equipment orders | CM&U segment profit | unknown |
| 9 `km-c-minservice-profit` | Mining after-sales service add segment profit; aftermarket carries a higher margin than new machines, so more aftermarket in the mix raises the segment margin (Komatsu (CM&U)) | aftermarket pricing holds; observable: the walk's volume and mix line | onset same quarter; build none; persists per unit; recognized segment profit | broker / inferred / unknown / inferred | non-genuine parts competition; service contracts priced below cost to win equipment orders | CM&U segment profit | unknown |
| 10 `km-a-op-cmu` | Identity: Komatsu CM&U segment result is one part of Komatsu operating profit (operating income by segment: segment profit plus corporate, eliminations and other operating items); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu operating profit | +1.04 sd/sd (accounting) |

Unresolved inputs: Indonesian coal contractors' fleet purchases (found not connected); Komatsu's share of mining-company fleet spending by commodity (not disclosed in reviewed sources); after-sales sales by region (not disclosed in reviewed sources); aftermarket margin versus new-equipment margin (not disclosed in reviewed sources); drop-through of mining new-equipment sales to segment profit (found connected); lag from mining capex to equipment orders and deliveries (not disclosed in reviewed sources); mining capex sensitivity to commodity prices (not disclosed in reviewed sources); mining equipment order backlog (not disclosed in reviewed sources); operating hours of Komatsu's installed mining fleet (not disclosed in reviewed sources).

#### Retail finance: equipment sales, finance book and debt

**Trigger:** more North American machines are sold on Komatsu finance. **Endpoint:** Komatsu operating profit.

Komatsu North America construction sales → Komatsu retail finance new contracts? → Komatsu retail finance assets → [earning_book] Komatsu retail finance revenue → [funding_need] Komatsu retail finance interest-bearing debt? → Komatsu retail finance interest expense → Komatsu retail finance costs → Komatsu retail finance segment result → Komatsu retail finance segment result → Komatsu operating profit  (? marks a step whose size is unknown)

The book earns revenue and is funded with debt: consolidated debt rising with the finance book is not industrial stress.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `km-c-nacon-rfnew` | Machines sold on Komatsu instalment or lease contracts are new finance contracts (mostly North America) (Komatsu finance subsidiaries) | finance penetration stable; observable: new contract volume; finance assets | onset at sale; build none; persists per sale; recognized balance sheet | inferred / inferred / unknown / unknown | customers finance with banks or pay cash | Komatsu retail finance new contracts | unknown |
| 2 `km.sf.rf_assets:komatsu.rf_new_contracts` | Komatsu retail finance assets (closing) = Komatsu retail finance assets (opening) + Komatsu retail finance new contracts - Komatsu retail finance collections, per 365 days: Komatsu retail finance new contracts flows into the stock each period; weight derived at the construction levels | unknown | onset each period; build accumulates; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | +1.05 sd/sd (stock-flow, accumulates per 365 days) |
| 3 [earning_book] `km-c-rfassets-rfrev` | Earning-book branch: a larger book earns more interest and lease income at its yield (Komatsu finance subsidiaries) | yield as it is; observable: Retail Finance revenue | onset as balances grow; build years; persists persistent; recognized segment revenue | documented / inferred / inferred / unknown | yield compression | Komatsu retail finance revenue | +0.62 sd/sd (identity) |
| 4 [funding_need] `km-c-rfassets-rfdebt` | Funding-need branch: the finance book is funded with debt, so gross debt rises with the book; that is not industrial stress (Komatsu finance subsidiaries (treasury)) | leverage of the book stable; observable: interest-bearing debt and finance assets | onset with origination; build none; persists contract term; recognized balance sheet | documented / inferred / unknown / unknown | securitization off balance sheet | Komatsu retail finance debt | unknown |
| 5 `km-c-rfdebt-rfcosts` | More debt carries more interest expense at the funding cost (Komatsu finance subsidiaries) | funding cost as it is; observable: interest on the finance debt | onset as drawn; build none; persists debt term; recognized segment profit | inferred / inferred / inferred / unknown | none (arithmetic at a given rate) | Komatsu retail finance interest expense | +0.75 sd/sd (identity) |
| 6 `km-a-rfcost-interest` | Identity: Komatsu retail finance interest expense is one part of Komatsu retail finance costs (Retail Finance costs: interest expense (a deduction) and other costs); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu retail finance costs | -0.69 sd/sd (accounting) |
| 7 `km-a-rf-revenue` | Identity: Komatsu retail finance revenue is one part of Komatsu retail finance segment result (Retail Finance segment: revenue less funding, credit and other costs); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu retail finance segment result | +1.60 sd/sd (accounting) |
| 8 `km-a-rf-costs` | Identity: Komatsu retail finance costs is one part of Komatsu retail finance segment result (Retail Finance segment: revenue less funding, credit and other costs); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu retail finance segment result | +1.20 sd/sd (accounting) |
| 9 `km-a-op-rf` | Identity: Komatsu retail finance segment result is one part of Komatsu operating profit (operating income by segment: segment profit plus corporate, eliminations and other operating items); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu operating profit | +0.10 sd/sd (accounting) |

Unresolved inputs: credit loss rate of the finance book (not disclosed in reviewed sources); retail finance assets (found not connected); retail finance interest-bearing debt (found connected); share of equipment sales financed by Komatsu (not disclosed in reviewed sources).

#### Japanese wages and fixed costs

**Trigger:** Japanese wage settlements rise. **Endpoint:** Komatsu operating profit.

Japan wage growth → Komatsu fixed costs? → Komatsu CM&U segment result? → Komatsu operating profit  (? marks a step whose size is unknown)

Wages sit in fixed cost; the walk's fixed-cost line is the observable.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `km-c-wage-fixed` | Higher Japanese wage settlements raise the cost of Japanese plants and staff, which sits in fixed cost (Komatsu (employer)) | wage settlements pass into pay; observable: the walk's fixed cost line | onset next pay round (April); build a year; persists persistent; recognized cost of sales and SG&A | inferred / inferred / unknown / unknown | productivity and automation offset | Komatsu fixed costs | unknown |
| 2 `km-c-fixed-profit` | Higher fixed costs lower segment profit one for one in the period (the walk's fixed-cost line) (Komatsu (CM&U)) | the costs sit in CM&U; observable: the walk's fixed cost line | onset same period; build none; persists persistent; recognized segment profit | documented / documented / unknown / documented | costs allocated to other segments | CM&U segment profit | unknown |
| 3 `km-a-op-cmu` | Identity: Komatsu CM&U segment result is one part of Komatsu operating profit (operating income by segment: segment profit plus corporate, eliminations and other operating items); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu operating profit | +1.04 sd/sd (accounting) |

Unresolved inputs: Japan labour-cost base (not disclosed in reviewed sources); fixed-cost base (not disclosed in reviewed sources).

#### Group bridge: operating income to net income

**Trigger:** operating income changes. **Endpoint:** Komatsu net income attributable to owners.

Komatsu operating profit → Komatsu income before income taxes → [tax] Komatsu income taxes → [minorities] Komatsu income attributable to non-controlling interests? → [identity] Komatsu net income attributable to owners → Komatsu net income attributable to owners → Komatsu net income attributable to owners  (? marks a step whose size is unknown)

Pretax income by identity, tax at the effective rate (calibrated), minorities (uncalibrated) and the net-income identity.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `km-a-pretax-op` | Identity: Komatsu operating profit is one part of Komatsu income before income taxes (pretax income: operating income plus non-operating items); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu income before income taxes | +1.05 sd/sd (accounting) |
| 2 [tax] `km-c-tax` | Income taxes are the effective rate times pretax income (a formula; the rate is an estimate) (accounting) | effective rate stable; observable: effective tax rate | onset same period; build none; persists while the rate holds; recognized income taxes | documented / documented / documented / documented | tax-rate changes; deferred tax; one-offs | Komatsu income taxes | -0.82 sd/sd |
| 3 [minorities] `km-c-nci` | Minority holders of consolidated subsidiaries take their share of those subsidiaries' profit (a larger negative) (accounting) | the change arises in subsidiaries with minority holders; observable: net income attributable to non-controlling interests | onset same period; build none; persists persistent; recognized net income | documented / documented / unknown / documented | the change arises in wholly-owned units | Komatsu income attributable to non-controlling interests | unknown |
| 4 [identity] `km-a-ni-pretax` | Identity: Komatsu income before income taxes is one part of Komatsu net income attributable to owners (net income: pretax income less taxes and minorities, plus equity in earnings of affiliates); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu net income attributable to owners | +1.27 sd/sd (accounting) |
| 5 `km-a-ni-tax` | Identity: Komatsu income taxes is one part of Komatsu net income attributable to owners (net income: pretax income less taxes and minorities, plus equity in earnings of affiliates); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu net income attributable to owners | +0.42 sd/sd (accounting) |
| 6 `km-a-ni-nci` | Identity: Komatsu income attributable to non-controlling interests is one part of Komatsu net income attributable to owners (net income: pretax income less taxes and minorities, plus equity in earnings of affiliates); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu net income attributable to owners | +0.14 sd/sd (accounting) |

Unresolved inputs: effective tax rate (found connected); minority share by subsidiary (not disclosed in reviewed sources).

#### Industrial machinery: semiconductor capex

**Trigger:** chipmakers raise wafer-fab equipment spending. **Endpoint:** Komatsu operating profit.

Wafer-fab equipment spending → Komatsu industrial machinery and others sales? → [revenue] Komatsu net sales → [profit] Komatsu industrial machinery and others segment result? → Komatsu operating profit  (? marks a step whose size is unknown)

Excimer-laser light sources follow lithography demand; presses follow carmakers' capex (not represented as a driver).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `km-c-semis-imo` | Chipmakers' fab-equipment spending orders lithography tools, which carry excimer-laser light sources (and their service) (chipmakers and lithography-tool makers) | light-source share holds; observable: wafer-fab equipment spending; segment sales | onset 1-3 quarters; build quarters; persists with the chip cycle; recognized net sales | broker / inferred / unknown / unknown | auto-industry press demand moves the segment the other way | Komatsu industrial machinery sales | unknown |
| 2 [revenue] `km-a-sales-imo` | Identity: Komatsu industrial machinery and others sales is one part of Komatsu net sales (net sales by segment, external customers, US GAAP); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu net sales | +0.09 sd/sd (accounting) |
| 3 [profit] `km-c-imo-profit` | Segment sales contribute segment profit at the contribution margin (Komatsu (IM&O)) | costs as they are; observable: segment results | onset same quarter; build none; persists per unit; recognized segment profit | documented / documented / unknown / documented | mix toward low-margin presses | Komatsu industrial machinery segment profit | unknown |
| 4 `km-a-op-imo` | Identity: Komatsu industrial machinery and others segment result is one part of Komatsu operating profit (operating income by segment: segment profit plus corporate, eliminations and other operating items); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu operating profit | +0.17 sd/sd (accounting) |

Unresolved inputs: industrial machinery sales sensitivity to semiconductor and manufacturing capex (not disclosed in reviewed sources).

#### Commodity prices and mining capex (hard rock)

**Trigger:** copper prices rise. **Endpoint:** Komatsu operating profit.

Copper price → [capex] Mining industry capital expenditure? → [utilization] Komatsu installed mining fleet operating hours? → Mining equipment demand? → Komatsu mining new-equipment sales? → [parts] Komatsu mining parts sales? → [service] Komatsu mining after-sales service? → Komatsu CM&U segment result → Komatsu CM&U segment result? → Komatsu CM&U segment result? → Komatsu operating profit  (? marks a step whose size is unknown)

Two clocks from one price: miners' capex buys new equipment after quarters (orders, lead times), while fleet hours lift parts and service sooner and more steadily. Mining new equipment drops through at the broker's rate (calibrated); the aftermarket at a higher, undisclosed margin. m32 (mining demand to operating profit) is the reduced form beside this path, never added to it.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [capex] `km-c-copper-capex` | Higher copper prices raise copper miners' cash flow and expected returns, so they approve expansions and fleet replacement (hard-rock demand) (copper miners) | prices expected to persist; balance sheets and permits allow expansion; observable: miners' capex guidance; commodity price curve | onset 2-4 quarters; build 1-2 years; persists with the commodity cycle; recognized miners' capex, then equipment orders | broker / broker / unknown / unknown | price spikes seen as temporary; miners' capital discipline (returns to shareholders first); permitting delays | mining industry capex | unknown |
| 2 [utilization] `km-c-copper-hours` | High copper prices keep marginal pits running and lift tonnes moved, so the installed fleet works more hours (mine operators and contractors) | mines not capacity- or weather-constrained; observable: production and overburden data; Komatsu telematics hours | onset 1-2 quarters; build quarters; persists with production; recognized parts and service demand | broker / inferred / unknown / unknown | transport bottlenecks (river barges), weather and quotas cap production; mine closures | installed mining fleet hours | unknown |
| 3 `km-c-capex-miningdemand` | Mining capex buys fleets: more capex means more orders for ultra-class trucks, shovels and loaders across the industry (mining companies (buyers)) | fleet purchases are part of the capex plan; observable: industry mining-equipment demand (company outlook, units y/y) | onset 1-2 quarters after approval; build a year; persists with capex; recognized orders and deliveries | broker / broker / unknown / unknown | capex spent on processing plants and infrastructure rather than fleets; leasing of fleets | industry mining equipment demand | unknown |
| 4 `km-c-miningdemand-equipment` | Industry mining-equipment demand becomes Komatsu new-equipment sales at its share, when machines are delivered (long lead times) (Komatsu mining sales (and distributors)) | share and production slots hold; observable: mining new-equipment sales in the results | onset at delivery; build quarters (lead times); persists with demand; recognized net sales when delivered | broker / broker / unknown / unknown | lost share; delivery slots or component shortages; order cancellations | Komatsu mining new-equipment sales | unknown |
| 5 [parts] `km-c-hours-miningparts` | More operating hours wear machines faster, so mines buy more parts (wear parts, components); the aftermarket follows utilization, not new-equipment orders (mine operators (Komatsu service network)) | machines under Komatsu service and parts supply; observable: mining after-sales sales in the results | onset 1-2 quarters; build quarters; persists with utilization; recognized net sales | broker / inferred / unknown / unknown | parts deferred by cash-strapped miners; competition from non-genuine parts | Komatsu mining parts sales | unknown |
| 6 [service] `km-c-hours-miningservice` | More operating hours wear machines faster, so mines buy more service (maintenance, rebuilds); the aftermarket follows utilization, not new-equipment orders (mine operators (Komatsu service network)) | machines under Komatsu service and parts supply; observable: mining after-sales sales in the results | onset 1-2 quarters; build quarters; persists with utilization; recognized net sales | broker / inferred / unknown / unknown | parts deferred by cash-strapped miners; competition from non-genuine parts | Komatsu mining after-sales service | unknown |
| 7 `km-c-mineq-profit` | Incremental mining new-equipment sales add segment profit at their drop-through (contribution margin after variable cost) (Komatsu (CM&U)) | fixed costs and prices as they are; observable: the walk's volume and mix line | onset same quarter; build none; persists per unit; recognized segment profit | broker / broker / broker / inferred | mix of machines; price concessions in a weak market; fixed-cost absorption changes with volume | CM&U segment profit | +0.38 sd/sd |
| 8 `km-c-minparts-profit` | Mining after-sales parts add segment profit; aftermarket carries a higher margin than new machines, so more aftermarket in the mix raises the segment margin (Komatsu (CM&U)) | aftermarket pricing holds; observable: the walk's volume and mix line | onset same quarter; build none; persists per unit; recognized segment profit | broker / inferred / unknown / inferred | non-genuine parts competition; service contracts priced below cost to win equipment orders | CM&U segment profit | unknown |
| 9 `km-c-minservice-profit` | Mining after-sales service add segment profit; aftermarket carries a higher margin than new machines, so more aftermarket in the mix raises the segment margin (Komatsu (CM&U)) | aftermarket pricing holds; observable: the walk's volume and mix line | onset same quarter; build none; persists per unit; recognized segment profit | broker / inferred / unknown / inferred | non-genuine parts competition; service contracts priced below cost to win equipment orders | CM&U segment profit | unknown |
| 10 `km-a-op-cmu` | Identity: Komatsu CM&U segment result is one part of Komatsu operating profit (operating income by segment: segment profit plus corporate, eliminations and other operating items); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu operating profit | +1.04 sd/sd (accounting) |

Unresolved inputs: Komatsu's share of mining-company fleet spending by commodity (not disclosed in reviewed sources); after-sales sales by region (not disclosed in reviewed sources); aftermarket margin versus new-equipment margin (not disclosed in reviewed sources); drop-through of mining new-equipment sales to segment profit (found connected); lag from mining capex to equipment orders and deliveries (not disclosed in reviewed sources); mining capex sensitivity to commodity prices (not disclosed in reviewed sources); mining equipment order backlog (not disclosed in reviewed sources); operating hours of Komatsu's installed mining fleet (not disclosed in reviewed sources).

#### Steel cost, pass-through and price realization

**Trigger:** steel prices rise. **Endpoint:** Komatsu operating profit.

Steel price → Komatsu material and purchased-component cost? → [absorb] Komatsu CM&U segment result? → [reprice] Komatsu CM&U selling-price realization? → [price] Komatsu CM&U segment result → [customer_response] Komatsu North America dealer retail sales? → Komatsu North America construction sales? → Komatsu CM&U segment result → Komatsu operating profit  (? marks a step whose size is unknown)

Cost inflation is absorbed or repriced (parallel branches); price realization drops through to profit, and loses some volume where competitors do not follow (counter-path). Gross effects are kept apart: never net the absorb and reprice branches before adding.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `km-c-steel-material` | Steel is the largest purchased input of heavy machinery (frames, buckets, components); a higher steel price raises material cost as supplier contracts reset (Komatsu purchasing and suppliers) | supplier contracts reset to market (quarterly or half-yearly); observable: the walk's material and variable cost line | onset 1-2 quarters; build a half-year (contracts and inventory); persists while prices hold; recognized cost of sales | documented / inferred / unknown / unknown | supplier cost-reduction programmes; steel price falls | Komatsu material cost | unknown |
| 2 [absorb] `km-c-material-profit` | Absorb branch: material-cost increases not recovered in price lower segment profit (Komatsu (CM&U)) | price not raised in step; observable: the walk's material and variable cost line | onset as inventory turns; build a quarter or two; persists until repriced; recognized cost of sales | documented / documented / unknown / documented | price pass-through (the reprice branch) | CM&U segment profit | unknown |
| 3 [reprice] `km-c-material-price` | Reprice branch: Komatsu raises list prices to recover cost inflation (a pricing decision) (Komatsu pricing) | competitors face the same costs; demand firm enough; observable: the walk's selling-price line | onset next price round (half-year); build 1-2 price rounds; persists sticky; recognized net sales when sold | documented / broker / unknown / unknown | competitors hold prices; weak demand forces discounts | Komatsu price realization | unknown |
| 4 [price] `km-c-price-profit` | Higher realized prices drop almost fully to segment profit, since the machines cost the same to build (Komatsu (CM&U)) | volume and cost unchanged; observable: the walk's selling-price line | onset when sold; build none; persists per unit; recognized segment profit | documented / documented / documented / documented | volume lost to the price rise (customer response branch) | CM&U segment profit | +0.78 sd/sd |
| 5 [customer_response] `km-c-price-nacon` | Customer response (counter-path): higher prices lose some orders to competitors or defer purchases; shown where pass-through is tested hardest, in North America (dealers and contractors) | competitors do not follow; buyers price-sensitive; observable: share data; dealer retail sales | onset 1-2 quarters; build quarters; persists unknown; recognized dealers' sales | broker / inferred / unknown / unknown | competitors raise prices too (shared tariff and steel costs); supply-constrained segments | North America dealer retail sales | unknown |
| 6 `km-c-retail-nacon` | Dealers reorder what they sell, so Komatsu's shipments (its North American construction sales) follow dealers' retail and rental-fleet sales (Komatsu dealers (ordering decisions)) | dealer stock at its target; observable: dealer orders against retail sales | onset one ordering cycle; build 1-2 quarters; persists with retail; recognized net sales when shipped | broker / inferred / unknown / unknown | dealers destock (the inventory branch) or restock | Komatsu North America construction sales | unknown |
| 7 `km-c-nacon-profit` | Incremental North American construction sales add segment profit at their drop-through (contribution after variable cost and tariffs) (Komatsu (CM&U)) | prices and costs as they are; observable: the walk's volume and mix line | onset same quarter; build none; persists per unit; recognized segment profit | broker / broker / broker / inferred | tariff cost per machine; price discounts to move dealer stock; the broker's figure implies a drop-through far below the segment margin | CM&U segment profit | +0.07 sd/sd |
| 8 `km-a-op-cmu` | Identity: Komatsu CM&U segment result is one part of Komatsu operating profit (operating income by segment: segment profit plus corporate, eliminations and other operating items); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu operating profit | +1.04 sd/sd (accounting) |

Unresolved inputs: North America dealer inventory (found connected); drop-through of US construction sales to segment profit (found connected); price elasticity of equipment demand (not disclosed in reviewed sources); price pass-through rate of cost increases (not disclosed in reviewed sources); prior-year CM&U sales (the base the selling-price line applies to) (found connected); steel price series and steel's share of cost of sales (not disclosed in reviewed sources).

#### Retail finance: funding cost and repricing

**Trigger:** US 2-year yields rise. **Endpoint:** Komatsu operating profit.

UST 2Y yield → Komatsu retail finance funding cost? → [funding] Komatsu retail finance interest expense → [repricing] Komatsu retail finance book rate? → Komatsu retail finance revenue → Komatsu retail finance costs → Komatsu retail finance segment result → Komatsu retail finance segment result → Komatsu operating profit  (? marks a step whose size is unknown)

Funding reprices as debt rolls; contract yields follow as the book turns over (a lag, so spreads compress first).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `km-c-ust2-funding` | The finance subsidiaries fund mostly in dollars at short and medium maturities, so their funding cost follows US short-to-medium yields as debt rolls (Komatsu finance subsidiaries (treasury)) | debt refinanced at market rates; spreads stable; observable: interest expense over average debt | onset as debt matures; build over the debt's average life; persists while rates hold; recognized interest expense | inferred / inferred / unknown / unknown | fixed-rate or swapped funding delays it | Komatsu retail finance funding cost | unknown |
| 2 [funding] `km-c-funding-rfcosts` | Funding branch: interest expense is debt times funding cost (Komatsu finance subsidiaries) | the debt balance as it is; observable: Retail Finance revenue less segment profit | onset as debt reprices; build debt life; persists while rates hold; recognized segment profit | inferred / inferred / inferred / unknown | matched funding: assets reprice too | Komatsu retail finance interest expense | +1.25 sd/sd (identity) |
| 3 [repricing] `km-c-funding-yield` | Repricing branch: new instalment and lease contracts are priced off funding cost plus a spread (a pricing decision), so yields follow with the book's turnover (Komatsu finance subsidiaries (pricing)) | competition from banks and dealers' own finance allows it; observable: new-contract yields | onset new contracts; build as the book turns over (years); persists contract term; recognized finance revenue over contracts | inferred / inferred / unknown / unknown | subsidized rates to support equipment sales hold yields down | Komatsu retail finance contract yield | unknown |
| 4 `km-c-yield-rfrev` | Higher contract yields raise interest income as the book turns over (Komatsu finance subsidiaries) | contracts written at the new yield; observable: Retail Finance revenue | onset new contracts; build years; persists contract term; recognized segment revenue | documented / inferred / inferred / unknown | volume falls | Komatsu retail finance revenue | +0.91 sd/sd (identity) |
| 5 `km-a-rfcost-interest` | Identity: Komatsu retail finance interest expense is one part of Komatsu retail finance costs (Retail Finance costs: interest expense (a deduction) and other costs); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu retail finance costs | -0.69 sd/sd (accounting) |
| 6 `km-a-rf-costs` | Identity: Komatsu retail finance costs is one part of Komatsu retail finance segment result (Retail Finance segment: revenue less funding, credit and other costs); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu retail finance segment result | +1.20 sd/sd (accounting) |
| 7 `km-a-rf-revenue` | Identity: Komatsu retail finance revenue is one part of Komatsu retail finance segment result (Retail Finance segment: revenue less funding, credit and other costs); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu retail finance segment result | +1.60 sd/sd (accounting) |
| 8 `km-a-op-rf` | Identity: Komatsu retail finance segment result is one part of Komatsu operating profit (operating income by segment: segment profit plus corporate, eliminations and other operating items); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu operating profit | +0.10 sd/sd (accounting) |

Unresolved inputs: pass-through of funding cost to contract yields (not disclosed in reviewed sources); retail finance assets (found not connected); retail finance funding mix and repricing (floating share, hedges) (not disclosed in reviewed sources); retail finance interest-bearing debt (found connected).

#### US tariffs: cost, pass-through and customer response

**Trigger:** the US raises tariffs on imported machinery, parts or steel-derivative content. **Endpoint:** Komatsu operating profit.

US effective tariff rate on imported machinery → Komatsu US tariff cost? → [reprice] Komatsu CM&U selling-price realization? → [absorb] Komatsu CM&U segment result → [price] Komatsu CM&U segment result → [customer_response] Komatsu North America dealer retail sales? → Komatsu North America construction sales? → Komatsu CM&U segment result → Komatsu operating profit  (? marks a step whose size is unknown)

Regime to customs cost; cost to management response (reprice or absorb, parallel); price to customer response; to segment profit. The absorb branch is calibrated as the gross cost (a yen of tariff cost is a yen of segment cost before recovery).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `km-c-tariff-cost` | A higher US duty on covered machines, parts and steel-derivative content raises what Komatsu's US importer pays at customs (US government (regime); Komatsu America (importer)) | covered origin and content; imported value; observable: tariff schedules; the company's disclosed tariff cost | onset customs entry; build as pre-tariff inventory sells; persists while the regime holds; recognized cost of sales when sold | documented / documented / unknown / inferred | exemptions and deals; refunds (a court-ordered refund of one tariff is in the company's figures); local production | Komatsu US tariff cost | unknown |
| 2 [reprice] `km-c-tariff-price` | Reprice branch: Komatsu raises US prices to recover tariff cost (a pricing decision); competitors importing into the US do the same (Komatsu America pricing) | competitors equally exposed; demand firm; observable: the walk's selling-price line; dealer price notices | onset next price round; build 1-2 price rounds; persists sticky; recognized net sales when sold | broker / broker / unknown / unknown | domestic US makers hold prices; demand slowdown | Komatsu price realization | unknown |
| 3 [absorb] `km-c-tariff-profit` | Absorb branch: the duty is a cost of sales of the US importer; before any price recovery each yen of tariff cost lowers segment profit by a yen (gross) (Komatsu America) | the cost is in CM&U; observable: the company's disclosed tariff cost against segment profit | onset when tariffed inventory sells; build one inventory turn; persists while the regime holds; recognized cost of sales | documented / documented / documented / inferred | price recovery (the reprice branch) offsets it: never net the two before adding | CM&U segment profit | -0.40 sd/sd |
| 4 [price] `km-c-price-profit` | Higher realized prices drop almost fully to segment profit, since the machines cost the same to build (Komatsu (CM&U)) | volume and cost unchanged; observable: the walk's selling-price line | onset when sold; build none; persists per unit; recognized segment profit | documented / documented / documented / documented | volume lost to the price rise (customer response branch) | CM&U segment profit | +0.78 sd/sd |
| 5 [customer_response] `km-c-price-nacon` | Customer response (counter-path): higher prices lose some orders to competitors or defer purchases; shown where pass-through is tested hardest, in North America (dealers and contractors) | competitors do not follow; buyers price-sensitive; observable: share data; dealer retail sales | onset 1-2 quarters; build quarters; persists unknown; recognized dealers' sales | broker / inferred / unknown / unknown | competitors raise prices too (shared tariff and steel costs); supply-constrained segments | North America dealer retail sales | unknown |
| 6 `km-c-retail-nacon` | Dealers reorder what they sell, so Komatsu's shipments (its North American construction sales) follow dealers' retail and rental-fleet sales (Komatsu dealers (ordering decisions)) | dealer stock at its target; observable: dealer orders against retail sales | onset one ordering cycle; build 1-2 quarters; persists with retail; recognized net sales when shipped | broker / inferred / unknown / unknown | dealers destock (the inventory branch) or restock | Komatsu North America construction sales | unknown |
| 7 `km-c-nacon-profit` | Incremental North American construction sales add segment profit at their drop-through (contribution after variable cost and tariffs) (Komatsu (CM&U)) | prices and costs as they are; observable: the walk's volume and mix line | onset same quarter; build none; persists per unit; recognized segment profit | broker / broker / broker / inferred | tariff cost per machine; price discounts to move dealer stock; the broker's figure implies a drop-through far below the segment margin | CM&U segment profit | +0.07 sd/sd |
| 8 `km-a-op-cmu` | Identity: Komatsu CM&U segment result is one part of Komatsu operating profit (operating income by segment: segment profit plus corporate, eliminations and other operating items); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu operating profit | +1.04 sd/sd (accounting) |

Unresolved inputs: North America dealer inventory (found connected); US tariff cost (found connected); covered import value and origin of US-sold machines (not disclosed in reviewed sources); drop-through of US construction sales to segment profit (found connected); price elasticity of equipment demand (not disclosed in reviewed sources); price pass-through rate of cost increases (not disclosed in reviewed sources); prior-year CM&U sales (the base the selling-price line applies to) (found connected).

#### US construction, rental channel and dealer inventory

**Trigger:** US nonresidential construction (data centres, power, infrastructure) rises. **Endpoint:** Komatsu operating profit.

US nonresidential construction spending → Komatsu North America dealer retail sales? → [reorders] Komatsu North America construction sales? → [sell_through] Komatsu North America dealer inventory → Komatsu North America construction sales? → [restock] Komatsu North America dealer inventory → [revenue] Komatsu construction equipment business sales → [profit] Komatsu CM&U segment result → Komatsu construction, mining and utility equipment sales → Komatsu net sales → Komatsu operating profit  (? marks a step whose size is unknown)

End demand pulls dealer orders and draws dealer stock down; elevated stock cuts orders until it normalizes (a stock-flow the method holds only as signed links). North America construction sales drop through at the broker's US rate (calibrated).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `km-c-nonres-nacon` | Nonresidential projects (data centres, power, infrastructure) need earthmoving, so contractors and rental fleets buy loaders, dozers, excavators and trucks from dealers (US contractors, rental companies and Komatsu dealers) | projects start on schedule; dealer stock not excessive; observable: construction put in place; rental utilization and fleet capex | onset 1-2 quarters; build quarters; persists with the project pipeline; recognized dealers' sales (off Komatsu's books) | broker / broker / unknown / unknown | financing costs delay project starts; rental companies buy aerial rather than earthmoving equipment | North America dealer retail sales | unknown |
| 2 [reorders] `km-c-retail-nacon` | Dealers reorder what they sell, so Komatsu's shipments (its North American construction sales) follow dealers' retail and rental-fleet sales (Komatsu dealers (ordering decisions)) | dealer stock at its target; observable: dealer orders against retail sales | onset one ordering cycle; build 1-2 quarters; persists with retail; recognized net sales when shipped | broker / inferred / unknown / unknown | dealers destock (the inventory branch) or restock | Komatsu North America construction sales | unknown |
| 3 [sell_through] `km.sf.dealer_inventory:komatsu.na_dealer_retail_sales` | Komatsu North America dealer inventory (closing) = Komatsu North America dealer inventory (opening) + Komatsu North America construction sales - Komatsu North America dealer retail sales, per 365 days: Komatsu North America dealer retail sales flows out of the stock each period; weight derived at the construction levels | unknown | onset each period; build accumulates; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | -2.23 sd/sd (stock-flow, accumulates per 365 days) |
| 4 `km-c-inventory-nacon` | When dealers carry more stock than demand needs, they order less from Komatsu (destocking), so shipments fall below retail sales until stock normalizes (Komatsu dealers (ordering decisions)) | dealer stock above the dealers' target; observable: dealer inventory against retail sales; Komatsu shipments | onset one ordering cycle; build 1-3 quarters; persists until stock normalizes; recognized net sales (shipments to dealers) | broker / broker / unknown / unknown | demand recovers and absorbs the stock; Komatsu supports dealers with floor-plan incentives | Komatsu North America construction sales | unknown; acts only while Komatsu North America dealer inventory is above 300 |
| 5 [restock] `km.sf.dealer_inventory:komatsu.north_america_construction_sales` | Komatsu North America dealer inventory (closing) = Komatsu North America dealer inventory (opening) + Komatsu North America construction sales - Komatsu North America dealer retail sales, per 365 days: Komatsu North America construction sales flows into the stock each period; weight derived at the construction levels | unknown | onset each period; build accumulates; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | +2.23 sd/sd (stock-flow, accumulates per 365 days) |
| 6 [revenue] `km-a-conreg-north_america` | Identity: Komatsu North America construction sales is one part of Komatsu construction equipment business sales (construction sales by customer region); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu construction equipment business sales | +0.56 sd/sd (accounting) |
| 7 [profit] `km-c-nacon-profit` | Incremental North American construction sales add segment profit at their drop-through (contribution after variable cost and tariffs) (Komatsu (CM&U)) | prices and costs as they are; observable: the walk's volume and mix line | onset same quarter; build none; persists per unit; recognized segment profit | broker / broker / broker / inferred | tariff cost per machine; price discounts to move dealer stock; the broker's figure implies a drop-through far below the segment margin | CM&U segment profit | +0.07 sd/sd |
| 8 `km-a-cmudem-construction` | Identity: Komatsu construction equipment business sales is one part of Komatsu construction, mining and utility equipment sales (CM&U sales by demand type (construction, mining)); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu construction, mining and utility equipment sales | +0.61 sd/sd (accounting) |
| 9 `km-a-sales-cmu` | Identity: Komatsu construction, mining and utility equipment sales is one part of Komatsu net sales (net sales by segment, external customers, US GAAP); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu net sales | +0.92 sd/sd (accounting) |
| 10 `km-a-op-cmu` | Identity: Komatsu CM&U segment result is one part of Komatsu operating profit (operating income by segment: segment profit plus corporate, eliminations and other operating items); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu operating profit | +1.04 sd/sd (accounting) |

Unresolved inputs: North America dealer inventory (found connected); US construction equipment demand response to nonresidential spending (not disclosed in reviewed sources); drop-through of US construction sales to segment profit (found connected).

#### US long rates and construction demand

**Trigger:** US 10-year yields rise. **Endpoint:** Komatsu operating profit.

UST 10Y yield → [residential] US housing starts? → [nonresidential] US nonresidential construction spending? → Komatsu North America dealer retail sales? → Komatsu North America dealer retail sales? → Komatsu North America construction sales? → Komatsu CM&U segment result → Komatsu operating profit  (? marks a step whose size is unknown)

Residential and nonresidential responses are parallel branches of one rate move; the rental channel partly offsets (renting instead of buying), not represented as a value.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [residential] `km-c-ust10-housing` | Higher long yields raise mortgage rates and developers' financing costs, delaying housing starts (homebuyers and developers) | mortgage rates follow the 10-year; observable: mortgage rates; starts | onset 1-2 quarters; build quarters; persists while rates hold; recognized starts | broker / broker / unknown / unknown | housing shortage supports starts; builders buy down rates | US housing starts | unknown |
| 2 [nonresidential] `km-c-ust10-nonres` | Higher long yields raise project financing costs, so marginal commercial projects are delayed (data centres and public infrastructure less so) (developers and project owners) | projects financed at long-term rates; observable: construction put in place; project start delays | onset 2-4 quarters; build quarters; persists while rates hold; recognized construction spending | broker / broker / unknown / unknown | AI data-centre and public infrastructure budgets are rate-insensitive | US nonresidential construction spending | unknown |
| 3 `km-c-housing-nacon` | Housing starts need site preparation and utilities work, so residential activity lifts demand for compact and mid-size earthmoving machines (homebuilders and site contractors) | starts translate into site work within the quarter; observable: housing starts; residential construction | onset 1-2 quarters; build quarters; persists with starts; recognized dealers' sales | broker / broker / unknown / unknown | starts shifting to multifamily (less earthmoving per unit); rental instead of purchase | North America dealer retail sales | unknown |
| 4 `km-c-nonres-nacon` | Nonresidential projects (data centres, power, infrastructure) need earthmoving, so contractors and rental fleets buy loaders, dozers, excavators and trucks from dealers (US contractors, rental companies and Komatsu dealers) | projects start on schedule; dealer stock not excessive; observable: construction put in place; rental utilization and fleet capex | onset 1-2 quarters; build quarters; persists with the project pipeline; recognized dealers' sales (off Komatsu's books) | broker / broker / unknown / unknown | financing costs delay project starts; rental companies buy aerial rather than earthmoving equipment | North America dealer retail sales | unknown |
| 5 `km-c-retail-nacon` | Dealers reorder what they sell, so Komatsu's shipments (its North American construction sales) follow dealers' retail and rental-fleet sales (Komatsu dealers (ordering decisions)) | dealer stock at its target; observable: dealer orders against retail sales | onset one ordering cycle; build 1-2 quarters; persists with retail; recognized net sales when shipped | broker / inferred / unknown / unknown | dealers destock (the inventory branch) or restock | Komatsu North America construction sales | unknown |
| 6 `km-c-nacon-profit` | Incremental North American construction sales add segment profit at their drop-through (contribution after variable cost and tariffs) (Komatsu (CM&U)) | prices and costs as they are; observable: the walk's volume and mix line | onset same quarter; build none; persists per unit; recognized segment profit | broker / broker / broker / inferred | tariff cost per machine; price discounts to move dealer stock; the broker's figure implies a drop-through far below the segment margin | CM&U segment profit | +0.07 sd/sd |
| 7 `km-a-op-cmu` | Identity: Komatsu CM&U segment result is one part of Komatsu operating profit (operating income by segment: segment profit plus corporate, eliminations and other operating items); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu operating profit | +1.04 sd/sd (accounting) |

Unresolved inputs: North America dealer inventory (found connected); US construction equipment demand response to nonresidential spending (not disclosed in reviewed sources); US housing starts series (not disclosed in reviewed sources); drop-through of US construction sales to segment profit (found connected).

#### Yen: disclosed sensitivity and its channels

**Trigger:** USD/JPY moves (a weaker yen). **Endpoint:** Komatsu operating profit.

USD/JPY → [disclosed_total] Komatsu operating profit → [disclosed_sales] Komatsu net sales → [transaction] Komatsu CM&U segment result? → [translation] Komatsu retail finance segment result? → [imported_inputs] Komatsu material and purchased-component cost? → Komatsu CM&U segment result? → Komatsu operating profit → Komatsu operating profit  (? marks a step whose size is unknown)

m30 (operating income) and km-c-usdjpy-sales (net sales) carry the company's disclosed per-yen sensitivities (calibrated). The transaction, translation and imported-input branches are their decomposition, uncalibrated: one calculation method at a time, never the aggregate plus its parts. EUR and AUD sensitivities are separate links (km-c-eurjpy-*, km-c-audjpy-*).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [disclosed_total] `m30` | Aggregate dollar-yen effect: a weaker yen raises consolidated operating income, mostly through dollar-invoiced machines and parts built in Japan (transaction), plus translation of overseas profits, less dearer imported inputs (Komatsu (exporter and consolidating parent)) | the plan's dollar exposure as it is; little hedging beyond the short term; observable: the company's published per-yen operating-income sensitivity and the walk's FX line | onset as rates apply to shipments and quarterly averages; build a quarter or two as hedges roll off; persists while the rate holds; recognized operating income of the quarter | documented / documented / documented / inferred | localization of production shrinks the export base; hedging delays it; the disclosed figure covers the plan's remaining quarters | Komatsu operating profit | +0.44 sd/sd |
| 2 [disclosed_sales] `km-c-usdjpy-sales` | Disclosed sensitivity: a weaker yen against the USD raises net sales as USD sales and profits translate into more yen (Komatsu (exporter and consolidating parent)) | the company's plan exposure in that currency; observable: the company's published per-yen sensitivity | onset as rates apply; build a quarter; persists while the rate holds; recognized the quarter's results | documented / documented / documented / inferred | hedging; changes in regional mix of the plan | consolidated net sales | +0.33 sd/sd |
| 3 [transaction] `km-c-usdjpy-transaction` | Transaction effect: machines and parts built in Japan and invoiced in dollars bring in more yen against yen costs (Komatsu (exporter)) | dollar-invoiced exports and dollar earnings as they are; observable: the walk's FX line; the company's disclosed per-yen sensitivity | onset as rates apply to shipments and quarterly averages; build a quarter or two; persists while the rate holds; recognized the quarter's results | documented / documented / unknown / inferred | localization of production; hedges delay it | Komatsu CM&U segment result | unknown |
| 4 [translation] `km-c-usdjpy-translation` | Translation effect: the US finance subsidiary's dollar profit translates into more yen (the sign follows the sign of the profit) (accounting (translation)) | dollar-invoiced exports and dollar earnings as they are; observable: the walk's FX line; the company's disclosed per-yen sensitivity | onset as rates apply to shipments and quarterly averages; build a quarter or two; persists while the rate holds; recognized the quarter's results | inferred / inferred / unknown / inferred | a loss translates into a larger yen loss | Komatsu retail finance segment result | unknown |
| 5 [imported_inputs] `km-c-usdjpy-imports` | Imported-input effect: dollar-priced components and materials cost more yen (Komatsu purchasing) | dollar-invoiced exports and dollar earnings as they are; observable: the walk's FX line; the company's disclosed per-yen sensitivity | onset as rates apply to shipments and quarterly averages; build a quarter or two; persists while the rate holds; recognized the quarter's results | inferred / inferred / unknown / unknown | commodity prices falling at the same time | Komatsu material and purchased-component cost | unknown |
| 6 `km-c-material-profit` | Absorb branch: material-cost increases not recovered in price lower segment profit (Komatsu (CM&U)) | price not raised in step; observable: the walk's material and variable cost line | onset as inventory turns; build a quarter or two; persists until repriced; recognized cost of sales | documented / documented / unknown / documented | price pass-through (the reprice branch) | CM&U segment profit | unknown |
| 7 `km-a-op-cmu` | Identity: Komatsu CM&U segment result is one part of Komatsu operating profit (operating income by segment: segment profit plus corporate, eliminations and other operating items); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu operating profit | +1.04 sd/sd (accounting) |
| 8 `km-a-op-rf` | Identity: Komatsu retail finance segment result is one part of Komatsu operating profit (operating income by segment: segment profit plus corporate, eliminations and other operating items); weight is its scale over the total's (accounting) | same period, perimeter and basis on both sides; never added to another view of the same total; observable: the reported reconciliation (parts plus residual and eliminations equal the total) | onset same reporting period; build none; persists identity; recognized quarterly results (cumulative over the fiscal year from April) | documented / documented / model / documented | a change of segment or region definition (the FY3/27 region reclassification restated Europe and the Middle East) | Komatsu operating profit | +0.10 sd/sd (accounting) |

Unresolved inputs: CNY, IDR and BRL sensitivities (not disclosed in reviewed sources); forward hedging of export receipts (not disclosed in reviewed sources); price pass-through rate of cost increases (not disclosed in reviewed sources); split of the disclosed yen sensitivity by channel (transaction, translation, imported inputs) (not disclosed in reviewed sources); steel price series and steel's share of cost of sales (not disclosed in reviewed sources).

## Validation

`tests/scenario/test_construction_komatsu.py` (loads sally_demo once; reads no client data):

- Structure: no `validate_construction` problems for the company; the twenty-one compositions and fourteen paths
  exist; one view drives each total, and the reconciling views are exactly the regions of CM&U sales (matrix
  columns), construction by product, mining by region and the walk; every path step has a transition, every causal
  step a next state, every uncalibrated step a sign and an "unknown" magnitude, every identity or stock-flow step a
  derived weight; the parallel responses of one driver are branches; the reduced forms (m31, m32, s45, s46) are never
  steps of their structural paths and keep their sizes.
- Financial integrity: every part of a driving view has a fixed-weight accounting link equal to its native sd over the
  total's, signed (interest expense deducted); a reconciling view's links are accounting and carry no weight; one unit
  per view; the views that leave something out keep a residual; every view reconciles at the prior medians within
  0.5% (`reconcile`); the matrix's sixteen cells add to their two row parts and eight column parts
  (`reconcile_matrices`); the four identities hold at the prior medians (`reconcile_identities`); both stock-flows have
  their flows linked to the stock, and the dealer roll-forward closes on a synthetic year (`reconcile_stock_flows`);
  dealer destocking is a stock with a threshold state; the gross tariff cost and its price recovery stay apart;
  finance-book debt is not industrial.
- Calibration: the only new sizes are the disclosed currency sensitivities, the gross tariff cost, the effective tax
  rate, the price drop-through and the two broker sensitivities; m30 reproduces the disclosed operating income per
  yen; every missing input says whether the supplied material was searched; no round-one conversion tag remains, and
  the steps no form fits stay uncalibrated with a note saying why.
- Generalization: an oil-price shock, for which no Komatsu path was written, traced through every link (below).
- Delivery: compositions in `financial_bridge`, named paths as `business_construction` transmission paths, accounting
  links as `accounting_identity`, uncalibrated links as `represented_uncalibrated` with their sign, m30's transition
  with documented magnitude in the export; new node ids from `/v1/world-models/sally_demo/graph`, the construction and trace
  endpoints.

Sally's expected paths (`tests/scenario/test_sally_expected_paths.py`) still pass.

**Generalization trace (oil-price shock, a Middle East disruption).** `trace(g, "oil.brent", "komatsu")`: 153 routes,
132 reach a financial endpoint (124 and 95 before the conversion), 37 of them quantified end to end. Calibrated end to
end: oil -> mining demand -> operating profit (m31, m32); oil -> Japanese CPI -> BoJ -> USD/JPY -> m30, and through
the Fed and US yields to the dollar, and through JPY/EUR to the EUR sensitivity. With one uncalibrated step: oil ->
mining demand -> new equipment -> segment profit. New since the conversion: US 2-year -> funding cost -> finance
interest expense (an identity step, so it now carries a size from the funding cost on); US 10-year -> construction ->
dealers' retail sales -> shipments and dealer inventory (a stock-flow); cost -> price realization -> the walk's price
line (an identity). Every route that stops short stops at the trace depth of eight links (21 routes: inside the
segment result, the dealer chain, the finance book and the price chain); none stops at a value with nothing leading
on. Mining's aftermarket is not reached: fleet hours have no oil or macro driver.

## Completion report

Outcomes map to the release outcomes: built and verified (**BV**: in the model and the export as an accounting
identity, identity, stock-flow or calibrated link), built but uncalibrated (**BU**: exported as
`represented_uncalibrated`, mechanism and sign, no size), blocked by a named input (**BL**), not built (**NB**).

| # | Outcome | What is in the model now | What remains |
|---|---|---|---|
| G01 | BV | `km.comp.segment_sales`, `km.comp.segment_profit` with corporate and eliminations | — |
| G02 | BV | demand-type and product views | aftermarket by region (not disclosed) |
| G03 | BV | eight regions x two demand types as the matrix `km.mx.cmu_sales`; construction driven through its regional cells, mining through products; FY3/26 restated baselines | — |
| G04 | BU / BV in part | `km.path.mining_capex`, `km.path.coal_contractors`; new-equipment drop-through calibrated (broker) | capex sensitivity to prices, lead times, Komatsu's share of fleet spending (not disclosed) |
| G05 | BU | `km.path.aftermarket` | fleet hours, aftermarket margin (not disclosed) |
| G06 | BU / BV in part | `km.path.us_construction`, `km.path.us_rates`; US construction drop-through calibrated (broker); dealer inventory a stock-flow; destocking with a threshold state | demand elasticities; dealer stock series and normal level (expert view only); destocking size |
| G07 | BU | `km.path.china_construction` | China excavator series; China margin |
| G08 | BV (aggregates) / BU (channels) | m30 from the disclosed sensitivity; sales, EUR and AUD links; channel branches uncalibrated | channel split, hedging, CNY/IDR/BRL (not disclosed); m30's export class (shared taxonomy): NB |
| G09 | BV | m31, m32 scoped as reduced forms | a structural oil-to-capex link (not disclosed) |
| G10 | BV | s45, s46 scoped (China a small share) | — |
| G11 | BU / BV in part | `km.path.price_cost`; price drop-through calibrated (documented); the walk's price line a product identity | pass-through, steel share, price elasticity (not disclosed) |
| G12 | BV in part / BU | gross tariff cost calibrated; reprice and customer response uncalibrated | covered import value and origin; pass-through |
| G13 | BU / BV in part | `km.path.retail_finance_rates`, `km.path.finance_book`; revenue and interest expense product identities; finance assets a stock-flow; RF debt bound | funding mix, repricing, finance assets and new contracts (to close the identities at actuals), credit losses |
| G14 | BU | `km.path.industrial_machinery` | segment sensitivity |
| G15 | BU | `km.path.fixed_costs` | labour-cost base |
| G16 | BV | `km.comp.cmu_profit_walk` (reconciling); the delta a difference identity; the price line a product identity | the other walk lines as identities (volume and mix, cost: not separable) |
| G17 | BV | pretax and net-income views; tax calibrated; minorities uncalibrated | minority share by subsidiary |
| G18 | BV | `sources.json` bindings and inspected dependencies (local) | — |
| G19 | BV | ten new market and policy entities, uncalibrated links | merge review of shared names |
| G20 | BV | objects present in the v4.1.4 export | — |
| G21 | BV | node ids served by the query, construction and trace endpoints | — |
| G22 | BV | the reconciling views and the matrix columns no longer collide with the driving view: the baselines bundle passes `bundles.py check` whole | — |
| G23 | BV | entity description | — |
| G24 | BV | `km.comp.retail_finance` an additive nested bridge; `km.comp.rf_costs` with interest deducted | — |

Counts: 24 gaps. By category (a gap can carry two): MC 16, CAL 9, MAP 5, EXP 1, RET 2. By outcome after the
Oct 18 conversion: BV 15 (G01, G02, G03, G09, G10, G16, G17, G18, G19, G20, G21, G22, G23, G24, plus G08's
aggregates); BV in part 6 (G04, G06, G08, G11, G12, G13); BU 4 (G05, G07, G14, G15); BL 0; NB 0 within this build's
files (m30's taxonomy class needs its owner).

### Conversion (Oct 18): one driving view per total, identities, stock-flows, a matrix, a threshold

**Driving view per total.**

| Total | Driving view | Reconciling (how) |
|---|---|---|
| CM&U sales | `km.comp.cmu_by_demand` | `km.comp.cmu_by_region` (columns of `km.mx.cmu_sales`) |
| Construction sales | `km.comp.construction_by_region` (the matrix cells) | `km.comp.construction_by_product` (`drives: false`) |
| Mining sales | `km.comp.mining_by_product` | `km.comp.mining_by_region` (`drives: false`) |
| CM&U segment result delta | `km.id.cmu_result_delta` (difference identity) | `km.comp.cmu_profit_walk` (`drives: false`) |
| Retail finance segment result | `km.comp.retail_finance` (nested bridge; revenue also in segment sales) | — |
| Retail finance costs | `km.comp.rf_costs` (interest deducted, other costs residual) | — |
| Every other total | its one view | — |

**Links converted, by form.**

- `product` identities: `km.id.price_effect` (the walk's price line = price realization x CM&U sales x 0.01; replaces
  the tagged `identity:` note on the price step), `km.id.rf_revenue` (`km-c-yield-rfrev`, `km-c-rfassets-rfrev`: assets x
  book rate), `km.id.rf_interest` (`km-c-funding-rfcosts`, `km-c-rfdebt-rfcosts`: debt x funding cost, now landing on
  interest expense rather than total finance costs).
- `difference` identity: `km.id.cmu_result_delta` (this year's segment result less last year's); replaces
  `km-c-walk-profit`, the change-to-level link that could not be sized.
- Stock-flows: `km.sf.dealer_inventory` (North American shipments in, dealers' retail sales out; replaces
  `km-c-nonres-inventory`, which drew stock from construction directly) and `km.sf.rf_assets` (new contracts in,
  collections out; `km-c-nacon-rfassets` became `km-c-nacon-rfnew`, sales to new contracts).
- Matrix: `km.mx.cmu_sales`, 2 demand types x 8 regions, 16 cells, rows driving.
- State: `km-c-inventory-nacon` (destocking) carries a threshold on dealer inventory; uncalibrated (no side sizes).
- Newly calibrated: `km-c-price-profit`, the drop-through of price realization on segment profit, from the company's
  walk (documented, the price line per point of realization).
- Left uncalibrated, with the reason in the note: `km-c-material-price` (asymmetric pass-through: no observed sizes for
  either side), `km-c-price-nacon` (the volume response to price: competitors' pricing unobserved),
  `km-c-funding-yield` (contract repricing: the book's turnover and the pass-through are not disclosed).

**Counts, before -> after** (links touching Komatsu's values, `check.py`): total 112 -> 137; calibrated (any size)
68 -> 74; uncalibrated 44 -> 63; accounting 53 -> 71; identity 0 -> 8; stock-flow 0 -> 4; state-dependent 0 -> 1.
By kind: weighted accounting 53 -> 46; reconciling accounting (no weight, never driving) 0 -> 25 (construction by
product 3, CM&U by region 8, mining by region 8, the walk 6); uncalibrated causal 44 -> 38; calibrated causal 15 ->
16 (`km-c-price-profit`); identity and stock-flow links (derived weights) 0 -> 12. The uncalibrated total rose only
because the reconciling views' accounting links are counted there; the causal steps without a size fell by six.

**Reconciliation now.** At the prior medians (`check.py sally_demo --entities komatsu --reconcile --statistic
median`): all 21 additive views exactly (0.00%), all four identities (finance revenue -0.10%, the rest 0.00%), and the
matrix's ten row and column lines; 0 flags. At the FY3/26 baselines (`--baselines <local baselines.json>`): 20 views
within 0.5% (the largest a 0.03% rounding difference), the matrix OK, the difference identity exact and the price
identity -0.22%; blocked, not flagged: the finance costs view and the two finance identities (interest expense,
finance assets and the book rate are not disclosed). The stock-flows need two dated stock levels, which the baselines
do not hold. `bundles.py check sally_demo <local baselines.json>`: OK, 64 items. Sources: 6 ids resolve; 111 links and
57 values cited; 0 material claims uncited.

**Inputs by status:** 8 found and connected, 2 found but not connected, 28 not disclosed in the reviewed sources,
0 not yet reviewed (unchanged by the conversion).

**Coverage per path now** (own steps; "Quantified" counts calibrated, identity, stock-flow and weighted accounting
steps).

| Path | Steps | Calibrated causal | Identity / stock-flow | Accounting | Uncalibrated (sign only) | Quantified steps |
|---|---|---|---|---|---|---|
| `km.path.aftermarket` | 9 | none | none | 5 | `km-c-hours-miningparts`, `km-c-hours-miningservice`, `km-c-minparts-profit`, `km-c-minservice-profit` | 5/9 |
| `km.path.china_construction` | 5 | none | none | 3 | `km-c-property-chinacon`, `km-c-chinacon-profit` | 3/5 |
| `km.path.coal_contractors` | 10 | `km-c-mineq-profit` | none | 1 | `km-c-coal-capex`, `km-c-coal-hours`, `km-c-capex-miningdemand`, `km-c-miningdemand-equipment`, `km-c-hours-miningparts`, `km-c-hours-miningservice`, `km-c-minparts-profit`, `km-c-minservice-profit` | 2/10 |
| `km.path.finance_book` | 9 | none | `km.sf.rf_assets:komatsu.rf_new_contracts`, `km-c-rfassets-rfrev`, `km-c-rfdebt-rfcosts` | 4 | `km-c-nacon-rfnew`, `km-c-rfassets-rfdebt` | 7/9 |
| `km.path.fixed_costs` | 3 | none | none | 1 | `km-c-wage-fixed`, `km-c-fixed-profit` | 1/3 |
| `km.path.group_bridge` | 6 | `km-c-tax` | none | 4 | `km-c-nci` | 5/6 |
| `km.path.industrial_machinery` | 4 | none | none | 2 | `km-c-semis-imo`, `km-c-imo-profit` | 2/4 |
| `km.path.mining_capex` | 10 | `km-c-mineq-profit` | none | 1 | `km-c-copper-capex`, `km-c-copper-hours`, `km-c-capex-miningdemand`, `km-c-miningdemand-equipment`, `km-c-hours-miningparts`, `km-c-hours-miningservice`, `km-c-minparts-profit`, `km-c-minservice-profit` | 2/10 |
| `km.path.price_cost` | 8 | `km-c-price-profit`, `km-c-nacon-profit` | none | 1 | `km-c-steel-material`, `km-c-material-profit`, `km-c-material-price`, `km-c-price-nacon`, `km-c-retail-nacon` | 3/8 |
| `km.path.retail_finance_rates` | 8 | none | `km-c-funding-rfcosts`, `km-c-yield-rfrev` | 4 | `km-c-ust2-funding`, `km-c-funding-yield` | 6/8 |
| `km.path.tariffs` | 8 | `km-c-tariff-profit`, `km-c-price-profit`, `km-c-nacon-profit` | none | 1 | `km-c-tariff-cost`, `km-c-tariff-price`, `km-c-price-nacon`, `km-c-retail-nacon` | 4/8 |
| `km.path.us_construction` | 10 | `km-c-nacon-profit` | `km.sf.dealer_inventory:komatsu.na_dealer_retail_sales`, `km.sf.dealer_inventory:komatsu.north_america_construction_sales` | 4 | `km-c-nonres-nacon`, `km-c-retail-nacon`, `km-c-inventory-nacon` | 7/10 |
| `km.path.us_rates` | 7 | `km-c-nacon-profit` | none | 1 | `km-c-ust10-housing`, `km-c-ust10-nonres`, `km-c-housing-nacon`, `km-c-nonres-nacon`, `km-c-retail-nacon` | 2/7 |
| `km.path.yen` | 8 | `m30`, `km-c-usdjpy-sales` | none | 2 | `km-c-usdjpy-transaction`, `km-c-usdjpy-translation`, `km-c-usdjpy-imports`, `km-c-material-profit` | 4/8 |

**Forecast coverage (Sally's theses).** Not rerun in this round (the forecasts are run centrally after the merge).
Before the conversion, the quantified share of routes to operating profit was 31.6% (S-T1), 28.6% (S-T3) and 50%
(S-T4). None of the converted links sits on those theses' Komatsu routes except the US-rate branch of the finance
arm (now quantified from the funding cost on through the interest identity), so the currency theses should be
unchanged and the rate legs of S-T1 and S-T3 should gain the finance result. Per-path detail: local `coverage.md`.

**What a downstream agent can now trace or calculate.** Net sales and operating income by segment; CM&U sales by
demand type, by product and as the region x demand-type matrix, each reconciled; the CM&U profit walk and its delta;
the finance segment as revenue (assets x book rate) less interest (debt x funding cost) and other costs; dealer
inventory and finance assets as stocks; pretax and net income. Calculated sizes for a yen move, for mining new
equipment or US construction sales on segment profit, for price realization on segment profit, for a tariff cost
(gross), for tax, and, through the identities, for a change in funding cost, finance debt, assets or book rate on the
finance result. Signed mechanisms for the rest.

## What the method could not express for an equipment maker

The October 18 method closed the first five items of the earlier list: a part in views of different totals (nested
bridges), the cross-classified sales (the matrix), levels and changes (the difference identity), products of states
(product identities) and stocks (stock-flows, with a threshold state). What still cannot be expressed:

1. **State-dependent responses without side sizes.** Destocking above a normal level, asymmetric cost pass-through and
   contract repricing all have a form now (threshold, asymmetry), but an asymmetry needs a size on each side and a
   threshold needs a calibrated link; the material gives neither, so they stay uncalibrated with the state recorded.
2. **Drivers on a reconciling view.** The Indonesian coal route acts on mining sales through the product view; the
   Asia mining cell is a column of the matrix and cannot take a driver of its own without a second route into mining
   sales. A matrix with drivers on cells in both directions is not supported.
3. **Two clocks on one driver.** New equipment follows capex after quarters; the aftermarket follows hours sooner.
   Timing on an uncalibrated link carries no weight, so a forecast cannot show the aftermarket cushioning first.
4. **Partial calibration biases the calculated part.** The tariff's gross cost is calibrated and its price recovery
   is not, so a calculated tariff forecast shows only the gross hit, a bound rather than an estimate.
5. **Disclosures on another basis or period.** The yen sensitivity is per ¥1 for the plan's remaining quarters; the
   broker's construction sensitivity is the US at its own base, applied to a North America value. `calibrate.py`
   takes one change at one level; the differences live in text.
6. **Currency crosses.** AUD/JPY has no driver from USD/JPY (no AUD/USD in the world). FX triangles could now be a
   ratio identity, but the AUD/USD value does not exist in this world.
7. **Identities blocked at actuals.** The finance identities hold at the priors but cannot be checked at actuals:
   finance assets, the book rate and interest expense are not disclosed in the reviewed sources; the stock-flows need
   two dated stock levels.
8. **Smaller frictions.** The walk's other lines (volume and mix, material and fixed cost) are attributions, not
   separable identities, so only the price line is one; the trace stops at a fixed depth inside the dealer and
   finance chains; the view vocabulary has no "channel" or "dealer" view (`operating_state` was used).
