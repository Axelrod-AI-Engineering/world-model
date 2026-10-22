# Business construction: methods for new inputs

<!-- toc -->
**Contents**

- [Calibrate a link from a disclosed sensitivity](#calibrate-a-link-from-a-disclosed-sensitivity)
- [Declare a stock split](#declare-a-stock-split)
- [Overlapping views at import](#overlapping-views-at-import)
- [Sources and citations that resolve](#sources-and-citations-that-resolve)
- [Search before declaring an input missing](#search-before-declaring-an-input-missing)
- [Reconciliation](#reconciliation)
- [Calculation coverage of a forecast](#calculation-coverage-of-a-forecast)
- [Identities: products, ratios, differences](#identities-products-ratios-differences)
- [Stocks and flows](#stocks-and-flows)
- [One driving view per total: reconciling views and matrices](#one-driving-view-per-total-reconciling-views-and-matrices)
- [State-dependent responses](#state-dependent-responses)
- [Calibrate from disclosed scenarios](#calibrate-from-disclosed-scenarios)
- [Trace through totals](#trace-through-totals)
- [Smaller additions and known gaps (Oct 18)](#smaller-additions-and-known-gaps-oct-18)
<!-- /toc -->

This page holds the method; the rules it serves are in [design/specificity.md](../design/specificity.md). Each
company's page holds its gap register and completion report (AIB Group, China Construction Bank, Citigroup, JPMorgan,
Komatsu, Morgan Stanley, MS&AD, SoftBank Corp, Tokio Marine, Toyota with its before-and-after of the review, and
UniCredit). Those pages are client content: they are local, not tracked, and live in the client root as
`docs/construction/<company>.md` (`WORLD_MODEL_CLIENT_DIR`, default `data/clients`; see
[the deployment guide](../guides/deployment.md#client-content)). A narrowed world of some covered companies and the
players they connect to is in [focus.md](focus.md) (Oct 18).

The company registers (Toyota's and Tokio Marine's, local) list gaps blocked by a named input. The
first three methods are what turns such an input into model structure when it arrives. They do not close a gap on their
own: each still needs its input. The next four (Oct 18) check a build: that its evidence resolves to documents, that
its missing inputs were searched for, that its numbers add up, and what a forecast's numbers are made of. The last six
(Oct 18, from the JPMorgan build, "what the method could not express for a bank") let the method say more
than "a part adds to its total".

## Calibrate a link from a disclosed sensitivity

A disclosure reads "a 1-unit move in X changes Y by Z", each value in its own native unit. A link's effect is in
target sd per source sd. Each value's `scale` is its sd in link space: native units for a Gaussian value, log units
for a lognormal one (a price, USD/JPY, a profit level). The changes are converted at the values' construction levels:

    z_X = (link(level_X + dX) - link(level_X)) / scale_X        (dX / scale_X for a Gaussian value)
    effect = z_Y / z_X

```
uv run python scripts/construction/calibrate.py sally_demo <interaction_id> \
    --source-change 1 --target-change 45 --evidence <source id> [--support documented|guidance|broker] \
    [--sd-range LO HI | --target-range LO HI] [--sigma-fraction 0.25] [--allow-sign-flip --reason "..."] [--write]
```

- **Spread.** A range is read as plus or minus two sigma, so sigma = (hi - lo) / 4. Give it in sd/sd (`--sd-range`)
  or as the disclosed range of the target change (`--target-range`). Without a range, sigma is a stated fraction of
  the effect (0.25 by default). The effect must lie inside its range.
- **What changes.** The link gets `effect: {mu, sigma}` and loses `calibration: uncalibrated`. Its transition records
  `evidence.magnitude` (documented, guidance or broker) and adds the source id to `evidence.sources`. With `--write`,
  only that interaction's keys change in the file that defines it (`construction/*.yaml`, else `interactions.yaml`).
  Comments, layout and the other entries stay as they are. Each edit is parsed back, and nothing is written unless
  exactly that one interaction changed.
- **What it prints.** The link before and after, both changes in sd, the units and levels used, and every forecast
  (a thesis of a scenario built on the world) whose `unquantified` list the link leaves. It also prints the
  uncalibrated links that now join that list because the shock reaches them. Reach follows quantified links and
  ignores the horizon, so it is an upper bound.
- **Refusals.** It refuses an unknown id; an accounting link (its weight is an identity); a link with no transition
  (the evidence goes there); a zero source or target change; a change that leaves a value's domain; and a sign that
  contradicts the transition's (or, without one, the current effect's). A contradicting sign goes through only with
  `--allow-sign-flip --reason`: the new sign and the direction's support are recorded on the transition, and the
  reason on the link's `note`.
- **Checks.** An effect above 3 sd/sd prints a warning to check the units. A link with no `kernel` keeps the default
  timing, and the script says so.

Code: `model/calibrate.py` (the method), `engine/construction_edit.py` (the exact edit).

## Declare a stock split

```yaml
# entities.yaml, on the entity
corporate_actions: [{type: split, ratio: 15, effective: 2026-04-01}]
# or a construction file, top level
corporate_actions: [{entity: tokio_marine, type: split, ratio: 15, effective: 2026-04-01}]
```

- **Basis.** The model holds every per-share value on the basis before every split its entity lists, so construction
  levels and history stay as they were set. Declare a split only if the value's construction level predates it.
- **Per share.** A value counts as per share if `features: {per_share: "true"}` is set or its unit says "per share" or
  "/share". A kind's default can carry the feature: sally_demo's `share_price` slot does.
- **At import.** An `observe`, or an `absolute` move, of a per-share value dated on or after a split's effective day
  is multiplied by the ratio of every split in force on that date. After a 15-for-1 split, a reported price of 400 is
  6,000 on the model's basis, not a 93% fall. A `relative` or `standardized` move has no unit and is unchanged. The
  import preview lists each conversion under `conversions`, and the review's rationale states it.
- **Validation.** The ratio is positive and not 1 (a reverse split is below 1). No two actions share a day. An entity
  with a split must have a per-share value.

Code: `model/corporate_actions.py`, `intake/bundle.py` (`signal_conversion`).

## Overlapping views at import

Two additive compositions of the same total (segments and regions both summing to operating profit) are two views of
one business. Each part has an accounting link to the total. If one import observes parts of both, both sets of links
carry the change into the total, and it counts twice.

- **Rule.** Within one item, and separately within one day (the items published that date, including those already
  imported), when observes or moves touch parts of two additive views of the same total, only one view's parts are
  folded. The view is chosen in this order: a view already folded that day (an approved change cannot be unfolded);
  else the view with the most distinct parts observed; on a tie, the larger share of its parts, then the first id.
  Every other signal of the item is folded as usual.
- **Visible.** The preview lists the held-back signals under each item's `dropped`, with the composition ids. It also
  returns `overlaps` (scope, item or day, total, views, the view kept, what was observed) and `overlap_rule`. The
  review's rationale says "Not folded: ...".
- **Why fold one view and not refuse the item.** Refusing would also hold back the item's unrelated signals (a
  results release reports segments, regions, guidance and the price together), and the reviewer would have to edit
  the bundle by hand. Folding one view never double counts, keeps what was dropped in view, and leaves the choice
  open: to use the other view, import an item without these parts.
- **Check.** `scripts/construction/check.py` prints each total with more than one driving additive view (`VIEWS ...`).
  `validate_construction` still reports a part that belongs to two additive views.
- **Reconciling views (Oct 18).** The guard applies only between driving views. Mark every view but one
  `drives: false`, or declare segments x lines as a matrix, and a results day folds whole: see
  [One driving view per total](#one-driving-view-per-total-reconciling-views-and-matrices).

Code: `intake/overlap.py`, applied in `sim/imports.py` (`preview`, `import_items`).

## Sources and citations that resolve

A tracked file names a source only by id (`evidence.sources: [ty.wb]`). The id resolves locally, in two files per
company under the client's folder (never tracked):

- `<company>/sources.json`: source id → `file`, `kind`, `publication_date`, `period`, `accounting_basis`, `read_state`,
  `proof_limits` (and `location` for one part of a file). The ids sit at the top level or under `"sources"`.
- `<company>/citations.json`: `{interaction or value id: [{source, location, passage}]}`. `location` is a sheet and
  cell, a table and row, or a page and paragraph. `passage` is the supporting text or cell, at most ~300 characters.

A claim is **material** when any of a transition's `existence`, `direction`, `magnitude`, or `timing` rests on
`documented`, `guidance`, `broker`, or `model`. A material claim needs a citation that gives a location.

```
uv run python scripts/construction/check.py sally_demo --entities toyota --sources data/work/sally/construction
uv run python scripts/imports/export_context.py sally_demo <out> --construction-sources data/work/sally/construction
```

- **The check** prints, per company, the source ids that resolve and the ones that do not (`UNRESOLVED`, with what
  cites them). It also prints the material claims without a located citation (`UNCITED`, with the claims) and citation
  keys that name nothing in the model. The scope is the links that touch the company's values, and its values.
  Passages never print.
- **The export** gives each relationship (company edge or macro link) whose transition names sources, or that is
  cited, `evidence_refs: [{source_id, document, location, passage}]`. Each cited value in the evidence pack gets the
  same. A cited id that no citation covers is listed at the document level, with `location: null`.
- **The source catalogue** is its own file, `source_catalogue_axelrod_<pack id>.json`, listed in the manifest's load
  order right after the evidence pack. It holds each source's document, kind, date, period, basis, read state, and proof
  limits. It is a file of its own, not a part of the evidence pack, because the catalogue describes the client's
  documents, not the model's state. One catalogue serves every evidence and forecast pack of the export.
- **Gaps** go under the domain pack's `domain_specific_support_objects.citation_gaps`: `unresolved_source_ids`,
  `claims_without_citation`, `unknown_citation_keys`, and `catalogue_problems` (an id two companies define). The same
  lists sit in the catalogue file, and the export script prints the counts. `schema_gaps` gains an entry for the
  references, which v4.1.4 has no field for.

Code: `context/construction.py` (`load_sources`, `citation_check`, `company_citations`, `evidence_refs`),
`context/v4.py` (`attach_sources`).

## Search before declaring an input missing

A transition's `unresolved` inputs each carry a status (`model/construction.InputNeed`). `not_disclosed_in_reviewed_sources`
needs the list of what was searched, so search first:

```
uv run python scripts/construction/inputs.py sally_demo --entities toyota --corpus data/sources/sally \
    [--files <file> ... | --dirs spreadsheets unpacked/sell_side/<company>] \
    [--extra-terms "eligible import volume=CBU imports,imported units"] [--exclude construction bench] [--top 5]
```

- **What it searches.** It takes every input of the links that touch the company's values, except those already
  `found_connected`. Files are `--files`, else every supported file under `--dirs`, else under `--corpus`. The parser is
  `axelrod_wm.ingest.parse`. Folders named in `--exclude` are skipped: by default, the builders' own `construction`
  notes and `bench`.
- **How it scores.** Each line of each page, sheet (a row), or slide is a passage. A passage scores 3 for each phrase
  it contains (the input's name and its extra terms), plus the share of the name's words it contains (stopwords
  dropped, plurals folded). A passage is a candidate only if it holds a phrase, or at least three in five of the words
  (two at minimum, or the only one). Candidates sort by score, then file, then location, so a rerun gives the same report.
- **What it writes.** `<corpus>/construction/<company>/input_search.json` and `.md`: per input, the queries, the
  files searched, and the best candidate passages with file and location. It refuses to write where git would track
  the report, since the passages are client text. It never edits a world file.
- **What it suggests.** Candidates found: `found_not_connected`. Read the passage, then bind it (a value, an
  observation, or a citation) and mark the input `found_connected`. Nothing found: `not_disclosed_in_reviewed_sources`,
  with `searched` = the files and `corpus: <query>` entries it ran.
- **The check** prints each company's inputs by status and every input still `not_yet_reviewed`.

Code: `context/construction.py` (`input_needs`, `inputs_by_status`, `search_inputs`, `search_markdown`).

## Reconciliation

An additive composition states that `total = members + residual + eliminations`. Each part counts with the sign of its
accounting link to the total. A deduction held as a positive level (funding cost, other expenses) has a negative link
and subtracts. An elimination is held negative with a positive link, or positive with a negative one.
`reconcile(graph, levels=None, tolerance=0.005)` checks each additive composition:

- **Levels.** The model's levels are its posterior means in native units (`model_levels(graph)`). A given
  `{value_id: level}` overrides them, for example `bundle_levels(bundle)`: each value's latest `observe` in an
  `axelrod.import/v1` bundle. The means of lognormal values need not add up when their medians do: a lognormal's mean
  is its median times exp(sigma^2 / 2). So round construction levels reconcile at `model_levels(graph, "median")`
  (`check.py --statistic median`) before they reconcile at the means.
- **Per composition.** It reports the total's level, the signed sum of the parts, the parts that subtract
  (`subtracted`), the difference (total minus sum) and the relative difference (over |total|), parts whose unit differs
  from the total's, and values without a level. `residual_to_close` is the residual's level that closes the gap: its
  level plus the difference, through the sign of its link, or the difference when the view has no residual.
- **ok or flag.** `ok` when every level is present, every part has the total's unit, and the relative difference is
  within the tolerance (0.5%). Otherwise `flag`.

```
uv run python scripts/construction/check.py sally_demo --entities toyota --reconcile \
    [--baselines data/work/sally/construction/toyota/baselines.json | --statistic median] [--suggest-residual] [--tolerance 0.005]
```

The check prints the table and exits 1 on any flag. Without `--baselines` it uses the model's levels; with it, each
bundle's observes. `--suggest-residual` prints the residual level that closes each flagged gap. Close a gap at the
priors by setting round levels that add up, with the residual absorbing the difference and saying so. Close it at the
baselines with the reported parts, or with an explicit "unexplained difference" residual whose size the report gives.
The export's `financial_bridge` carries each composition's `reconciliation` at the model's levels (null for a
non-additive view).

Code: `model/construction.py` (`reconcile`, `model_levels`, `bundle_levels`).

## Calculation coverage of a forecast

A forecast's `coverage` (in the API's forecast and brief, and the v4 forecast pack's `calculation_coverage`) splits the
links out of every value the shock reaches:

- **`contributed`**: the quantified links that ran, with `contribution_sd`, what each added to its target at the horizon.
- **`excluded`**: the links that carry no size here, with `reason`. `uncalibrated` comes with its sign and mechanism.
  `absent_in_every_scenario` means every scenario turned the link off. `outside_the_forecast_networks` means no
  isolated network holds the link.
- **`blocking_inputs`**: the excluded links' unresolved inputs, with status.
- **`targets`**: per target, the routes from a shocked value (at most six links, calibrated or not), the fully
  quantified ones, and their share. The company's own construction is counted apart, so a high share cannot hide a
  path whose own steps are unsized: `own_steps` (distinct links inside the target's company on any route),
  `own_steps_quantified`, `share_own_steps_quantified`, `own_steps_unquantified`, and the quantified routes split into
  `quantified_routes_through_own_steps` and `quantified_routes_through_summary_links_only` (macro or reduced-form
  links straight to the total).

`unquantified` is unchanged: the uncalibrated links reached, with what lies downstream. See [the API](../api/README.md#simulations).

Code: `inference/task.py` (`forecast_coverage`, `channel_contributions`).

## Identities: products, ratios, differences

Many economics are exact and not sums: NII = balance x rate, NIM = NII / earning assets, CET1 ratio = CET1 / RWA,
revenue = units x price, NII ex Markets = NII - Markets NII. Declare the identity; its links' weights are derived.

```yaml
identities:
  - {id: acme.id.nii, entity_id: acme, form: product, target: acme.nii,
     factors: [acme.earning_assets, acme.nim], coefficient: 0.01, unit_check: "USD bn = USD bn x % x 0.01"}
  - {id: acme.id.cet1, entity_id: acme, form: ratio, target: acme.cet1_ratio,
     numerator: [acme.cet1_capital], denominator: [acme.rwa], coefficient: 100}
  - {id: acme.id.nii_ex_mkts, entity_id: acme, form: difference, target: acme.nii_ex_markets,
     of: acme.nii, minus: [acme.markets_nii]}
```

- **Weights.** A product or ratio holds in log space, d ln y = sum e_i d ln x_i (e = +1 a factor or numerator, -1 a
  denominator). With k_v = d ln v / dz (the scale for a lognormal value; scale / level for a Gaussian one, linearized
  at its construction level; scale x (1 - level) for a logit one), w_i = e_i k_i / k_y. A difference holds in native
  units: w_i = sign_i m_i / m_y, with m_v = dv / dz. A level of zero cannot be linearized and is refused.
- **Links.** Each term gets an `edge_type: identity` link to the target, named `<identity id>:<term>`, with a
  generated transition (support "inferred"). To carry your own transition or kernel, write the link with
  `edge_type: identity` and `identity: <id>`, and no effect: a written effect is refused.
- **Engine.** Like accounting links: fixed (fold, process noise and kernel learning never change them), existence
  ~1, same period (kernel delay 0, lag 1). The weight is linearized at the construction levels, not re-linearized
  as levels move.
- **Check.** `validate_construction` requires one identity link per term naming the identity, and no stray ones.
  `reconcile_identities` compares the target's level with what its terms imply (`check.py --reconcile`). Units are
  free text, so the unit algebra is stated in `unit_check` and tested through the levels: a rate held in % without
  its 0.01 misses by 100x. A difference's terms must share the target's unit.
- **Export.** `dependency_type: accounting_identity` (the v4.1.4 contract has no enum for it), with
  `axelrod.identity` (form, formula, role); the identities with their formulas and reconciliation under
  `domain_specific_support_objects.financial_identities`.

## Stocks and flows

```yaml
stock_flows:
  - {id: acme.sf.cet1, entity_id: acme, stock: acme.cet1_capital, period_days: 91,
     inflows: [acme.net_income], outflows: [acme.dividends, acme.buybacks]}
```

- **Weights.** Flows are measured per period. w = +-m_flow / m_stock: the stock's sd added per period by a flow held
  one sd above its level. Outflows are held positive and subtract; a flow held negative (a cost) is an inflow.
- **Engine.** The link's kernel has `shape: accumulate`: a ramp over the period that never levels off, so the stock
  integrates the flow (phi = (1 / period) x the sum of the flow's past deviations, after the delay; see
  `dynamics/kernels.py`). Daily propagation, the fold's regressors, the Monte Carlo forecasts and the synthetic world
  all run it; its period and delay are exact, never drawn. Only deviations accumulate: the flow at its construction
  level is the stock's own baseline path, not added by the link. The weight is linearized at the construction levels.
- **Check.** `reconcile_stock_flows(graph, bundle_series(bundle))` checks closing = opening + inflows - outflows
  between each pair of dated stock levels, summing the flows dated in between (`check.py --reconcile --baselines`).
  The model's own levels (one per value) cannot check a roll-forward.
- **Export.** `dependency_type: accounting_identity`, `axelrod.identity` with the roll-forward, the period, and how
  it computes; the stock-flow under `financial_identities` with `form: stock_flow`.

## One driving view per total: reconciling views and matrices

A company reports several views of one total on the same day (segments and regions; revenue by region and by customer
location; segments and lines). Exactly one view drives a total. The others reconcile:

```yaml
compositions:
  - {id: acme.comp.segments, total: acme.op, members: [...], ...}            # drives: true (the default)
  - {id: acme.comp.regions, total: acme.op, members: [...], drives: false}   # reconciling: no quantified links to the total
matrices:
  - id: acme.mx.revenue
    entity_id: acme
    rows: acme.comp.segments        # drives the total
    columns: acme.comp.lines        # passive, like drives: false
    cells: {acme.ccb: {acme.nii: acme.ccb_nii, acme.fees: acme.ccb_fees}}   # optional
```

- **Rule.** `validate_construction` flags a total with two driving views, a reconciling view whose part has a
  quantified link into the total (an uncalibrated one carries nothing and may stay), and a matrix whose driving view
  is marked `drives: false`.
- **Matrix.** Rows x columns, each cell optional. Each cell has accounting links to its row part and its column part;
  drivers attach to cells, and the driving view carries the change into the total. `reconcile_matrices` checks each
  part whose cells are complete against the sum of its cells.
- **Total excluding a part** (NII ex Markets): a `difference` identity, not an elimination value.
- **Import.** A reconciling view's parts are never dropped by the overlap guard: a results day that reports every
  view folds whole. Two driving views of one total (pre Oct 18 worlds) are still guarded as before.
- **Export.** `financial_bridge[].role` is `driving`, `reconciling` or `non_additive`, with `matrix_id`; matrices
  under `financial_matrices` with their cell reconciliation. `reconcile()` rows carry the role too.

## State-dependent responses

```yaml
- id: acme-deposit-beta
  source: us.fed_funds
  target: acme.deposit_cost
  state:
    asymmetry: {rises: {mu: 0.6, sigma: 0.1}, falls: {mu: 0.35, sigma: 0.1}}   # optional value:, at: (native)
    threshold: {value: acme.cet1_ratio, above: 11.5}                           # acts only above (or below:)
    sign_flip: {value: acme.new_minus_book_yield, at: 0.0, positive: above}    # stated sign above, reversed below
```

- **Semantics.** Each compiles to a `piecewise` moderator of the interaction model: the full effect on one side of a
  value's level, gamma x the effect on the other (asymmetry: gamma = falls / rises, about the source's construction
  level unless `at` is given; threshold: 0; sign flip: -1). Levels are native and convert to the moderator's standard
  units at its construction level. The moderator reads the value the day before, as every moderator does.
- **Rules.** An asymmetric link writes no `effect` (its sizes are its asymmetry) and is calibrated.
- **calibrate.py.** `--side rises|falls` sizes one side (the other keeps its size: the asymmetry's, else the link's
  current effect; refused when it has none). `--stop-when VALUE above|below LEVEL` and `--flip-when VALUE
  above|below LEVEL` write the condition a disclosure states.
- **Export.** `axelrod.state` with the conditions and their words.

## Calibrate from disclosed scenarios

Banks disclose earnings-at-risk as scenarios (parallel +100bp, steeper curve); an insurer discloses a net asset
sensitivity that several links share. Each scenario is one equation, z_Y = sum_l effect_l x z_X(l); the sizes are the
least-squares solution:

```yaml
# disclosure.yaml
target: acme.pretax
links: [acme-short-end, acme-long-end]      # each into the target
split: [acme-short-end]                     # optional: sized separately for rises and falls
evidence: acme.co
support: documented
scenarios:
  - {id: parallel_up_100, changes: {us.fed_funds: 1.0, us.ust10: 1.0}, target_change: 2.9}
  - {id: parallel_down_100, changes: {us.fed_funds: -1.0, us.ust10: -1.0}, target_change: -3.4}
  - {id: steeper, changes: {us.ust10: 1.0}, target_change: 0.9}
```

```
uv run python scripts/construction/calibrate.py sally_demo --disclosure disclosure.yaml [--write]
```

- **Refusals.** Fewer scenarios than sizes, a rank-deficient design ("underdetermined", naming the sizes), a size no
  scenario moves, a scenario moving a value none of the links carries, a link that points elsewhere or is fixed, and a
  sign that contradicts a link's (unless `--allow-sign-flip --reason`).
- **Spread.** With spare scenarios, sigma is the least-squares standard error; with an exact fit, a fraction of the
  effect. A split or already-asymmetric link uses the side each scenario moves its source to.
- **Recorded.** Each link's `note` names the scenarios it was sized over and the links sized with it; its transition
  records the support and the source. The basis of the disclosure (pretax, static balance sheet, ex Markets) is the
  builder's to match: choose a target value on that basis.

## Trace through totals

`trace(graph, start, entity, max_depth=8, through_totals=False)` stops at the first total a route reaches. With
`through_totals=True` (API `?through_totals=true&max_depth=`, `check.py --through-totals`) it keeps the route up to
each total and goes on through it, within the depth bound; each route lists the totals it `passes`. Identity targets
and stocks are endpoints too.

## Smaller additions and known gaps (Oct 18)

- **Notes.** An interaction's `note` (conversion tags, a flip's reason, the scenarios a size came from) now loads into
  the graph and exports under `axelrod.note`. A conversion that is an identity belongs in `identities:` or
  `stock_flows:`, which derive the weight; a note only records it.
- **Proxy inputs.** `status: found_proxy` (with `found_in`: the sector or peer source, and the `note`: what it stands
  in for) marks an input found only at sector or peer level, apart from `not_disclosed_in_reviewed_sources`.
- **Calendar timing.** `transition.timing.calendar` ("mortgage rates reset on 1 January") records an administered
  date and exports with the transition. Gap: the engine's kernels count days from the change, so a repricing date is
  not scheduled; set the kernel's delay to the expected days until the date and say so.
- **Nested bridges.** A value may be a part of bridges of different totals (a segment's revenue in group revenue and
  in its own segment profit bridge). Only two additive views of the same total overlap.
- **Attributable share.** Owners' profit = subsidiary profit x economic share is a `product` identity: a constant
  share is its `coefficient` (0.6), a share that moves is a factor value.
- **Period-average stocks.** `stock_flows[].measure: period_average` (average subscribers) delays the accumulation
  by half a period (an approximation, stated in the formula); its roll-forward is not reconciled, since an average
  has no closing level to check.
- **Peer sizes.** `support: peer` (calibrate.py `--support peer`) labels a size transferred from a named comparable
  company: material (it needs a citation) and, without a range, a wider spread (half the effect).
- **Proxy series.** `features: {proxy_for: "EUR swap 10Y"}` on a value says it stands in for a missing series; the
  view lists it.
- **Dormant paths.** `paths[].active_when: "once the state stake is zero"` marks a conditional path; the view and the
  export state it.
- **Weighted averages.** `form: weighted_average` with `weights: {value: w}` (stated, summing to 1): a currency
  basket's rate. Linear like a difference: w_i x m_i / m_y. Gap: weights that are themselves values (a portfolio loss
  rate = sum share_i x rate_i) are a sum of products; hold each product as an identity and the sum as a composition.
- **Blocked, not flagged.** A reconciliation with a missing level is `blocked` (with `blocked_by`, the values without
  a level), not `flag`: nothing to compare is not a discrepancy. check.py counts only flags toward its exit code and
  prints the blocked count.
- **Public but not supplied.** `support: public_not_supplied` (a claim the company discloses publicly, not in the
  supplied material) and the input status `disclosed_not_supplied` (it needs `searched`; say where in the `note`),
  apart from `not_disclosed_in_reviewed_sources`.
- **Extraction keywords.** check.py prints `KEYWORD` for a value whose head word (the last word of its id's slot, or
  of its name without the company's words) is a common English word: the ingest gazetteer would match it anywhere
  ("securities held" made "held" a keyword). `context/construction.keyword_risks`.
- **Joint shocks.** An all-currency sensitivity is one scenario moving several sources; scenario calibration
  attributes it across their links when other scenarios separate them (else it is refused as underdetermined).
- **Horizon-dependent responses.** A book neutral in year one and positive in year two is two links from one source:
  one with a short decaying kernel and one delayed. A single link's sign cannot change with the horizon.
- **Gap: shared market states on a company.** A market state built on one company's entity (claims severity on
  tokio_marine) cannot be moved to a market entity from a construction file; move it in entities.yaml and update its
  links' ids.
- **Gap: bounded accounting weights.** A disclosed total with an undisclosed split has parts whose weights are unknown
  but bounded. Hold them as uncalibrated accounting links with the bound in the transition; a weight interval is not
  built.
- **Gap: ratchets and dated events.** A response that never reverses (a dividend that is never cut) is approximated by
  an asymmetry with `falls: {mu: 0}` about the construction level, not about the running maximum. A price rise or a
  commissioning on a date is a scheduled event (a scenario's shock), not a link.
- **Policy substitution.** A fiscal subsidy that lowers the odds of a rate cut has no relation type. A link into a
  decision variable reads as a move of the rate itself, and the state-dependent forms change a link's size, not a
  decision's probability. Gap: a "decision odds" relation, scoring a decision's distribution, is not built.

Code: `model/construction.py` (objects, weights, checks, reconciliation), `engine/initialize.py`
(`compile_construction`), `dynamics/kernels.py` and `dynamics/propagation.py` (accumulation, piecewise moderators),
`model/calibrate.py` and `engine/construction_edit.py` (sides, conditions, scenarios), `intake/overlap.py`,
`context/construction.py` (view, trace), `context/v4.py` (export).
