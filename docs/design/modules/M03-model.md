# M03 · Model

| | |
|---|---|
| Layer | 1 · Domain |
| Status | **Exists**; merge `events/` into it, and move `PosteriorUpdater` out to [M08](M08-dynamics.md) |
| Code today | `model/` (about 1.9k lines), `events/` (market events, graph update events, theses) |
| Target | `axelrod_wm/model/` with `objects/` (entity, interaction, superentity, taxonomy, hypothesis), `values/` (distributions, kernels, temporal), `events/` (market, graph_update, thesis), `records/` (evidence, explanation, forecast) |

## Purpose

The data model: pure pydantic types with indexes and no inference. Everything the system knows is one of these types, and everything it writes is a change to one of them.

## Owns

**Objects in the graph.** Terms follow [glossary.md](../glossary.md).

| Type | Key fields | Notes |
|---|---|---|
| `Entity` | id, name, kind (company, person, agency, market, macro_factor, external_factor, other), aliases, category_tags, features, subentity_ids, internal_interaction_ids, generalization_id, origin, created_at | An actor or an idea. It is itself a small graph of subentities. |
| `Subentity` | id = `<entity>.<slug>`, entity_id, name, attribute_kind, unit, aliases, features, scale, obs_noise, prior, posterior, anchor, level_mean, level_var, level_noise, observed, origin, history, prior_source_id, state_cov, constraint, user_confidence | One of an entity's values. z = (link(x) − anchor) / scale. |
| `EconomicConstraint` | soft bounds in native units | Soft economic constraints (a yield caps near 100%, share is held down by supplier diversification) |
| `Interaction` | id, source_id, target_id, label, direction, edge_type, origin, existence (Beta), forward and reverse `EdgeDynamics(effect, kernel)`, parameters, evidence, time_states, generalization_id, internal, tags, created_at, retired_at | A directed causal relation between two subentities. Never called a "link" in the UI. |
| `KernelSpec` | delay, lag, duration (distributions) | Step response: zero before the delay, a ramp over the lag, then a fade over the duration |
| `ParameterBinding` | name, moderator_id, form (multiplicative, threshold, additive), coefficient, threshold | A third input that moderates a binary interaction |
| `SuperentityPattern` | roles, relations (`present` flag), sub_pattern_ids, support, status (candidate, admitted, dissolved), rival_ids, episode_ids, track_record, generalization_id | A reusable configuration of entities, interactions, and other superentities. Lives in LTM. |
| `SuperentityInstance` | pattern_id, bindings (role → entity), interaction_ids, absent_interaction_ids, child_instance_ids, activation, transient | A pattern bound in WM |
| `SuperInteraction` | kind (causal, shares_members) | An abstraction over the boundary interactions between two instances |
| `Taxonomy`, `Generalization`, `GeneralizationStats`, `Signature`, `AttributeVocabulary` | | Kinds: the object and interaction taxonomies |
| `Hypothesis` | kind, statement, interaction or source and target, decision subentity, change, and window, probability, informational_value, scored_at, half_life_days (14), status | Members of the hypothesis frontier |
| `CausalGraph` | entities, subentities, interactions, instances, with indexes | A pure data structure, with no inference |

**Distributions and time.** `Gaussian`, `Beta`, `LogNormal`, `Gamma`, `Link` (identity, logit, log), `DistSummary`, `Observation`, `TimeState`, `Bitemporal`.

**Events.**

| Type | Key fields |
|---|---|
| `MarketEvent` | id, kind, channel (scraper, data_feed, user; imported items arrive as user events), published_at, occurred_at, headline, body, url, source |
| `GraphUpdateEvent` | id, kind (real, hypothetical), ops, specificity, market_event_id, evidence |
| Operations | `AddEntity`, `AddSubentity`, `ObserveValue`, `ChangeValue` (absolute, relative, standardized; step or pulse; `intervention` = do()), `AddInteraction`, `ReweightInteraction`, `AnnotateInteraction`, `ProposeHypothesis`, `ProposeSuperentity`, `DissolveSuperentity`, `RetireEntity`, `RetireInteraction` |
| Targets | `ConcreteTarget`, `AbstractTarget`; `Specificity` = generalization (0), entity (1), subentity (2) |
| `Thesis` | id, question, mode (open_ended, scaffolded), event (hypothetical), horizon_days (182), targets, target_groups (entities, superentities, sectors, categories), posed_by, posed_at, pinned |

**Records.** `Evidence`, `Explanation`, `PathContribution`, and (moved here from `inference/records.py`) `Forecast`, `ForecastScenario`.

## Additions this design makes

These are additive fields. Old snapshots load with the defaults.

| Addition | On | Borrowed from | Why |
|---|---|---|---|
| `valid_from`, `valid_to`, `recorded_at` | every `TimeState`, `Interaction`, `Evidence` | Semantica `BiTemporalFact` | "What did the model believe on date X about date Y". Backtests without leakage. |
| `vintage`, `reference_period`, `release_ts` | `ObserveValue`, `Evidence` | ml-roadmap R15 | Point-in-time data |
| `evidence_type` (observational, natural experiment, analyst, reviewed article, user) | `Evidence` | ml-roadmap R11 | Weigh evidence by how it was obtained |
| `source_credibility`, `trust_tier` (quarantine, bronze, silver, gold) | `Evidence` | Semantica's conflict and trust model | Show in review how corroborated a claim is |
| `identity` (declared identity fields, for example ticker or LEI) | `Entity` | Cognee `identity_fields` | One real actor, one id, across imports |
| `superseded_by`, `supersession_reason` | `Interaction`, `TimeState` | Cognee temporal contradictions | Supersede, never delete, so history stays readable |
| `expectation` (consensus, whisper, OIS or futures-implied) | `ObserveValue` | ml-roadmap R13 | Read releases as surprises (pricing in) |

## Interface

Types only, plus pure helpers:

```python
CausalGraph.entity(id) / .subentity(id) / .interaction(id) / .instance(id)
CausalGraph.incoming(subentity_id) -> list[Interaction]
CausalGraph.outgoing(subentity_id) -> list[Interaction]
Interaction.significance() -> float          # existence × |effect|
Interaction.confidence() -> float
GraphUpdateEvent.specificity -> Specificity   # the lowest over its ops
Distribution.mean / .sd / .quantile(q) / .summary() -> DistSummary
```

## Depends on / used by

- Depends on: [M01](M01-core.md).
- Used by: everything above it.

## Invariants

- **No logic beyond the types.** No module in `model/` imports numpy-heavy algorithms, the registry, or state. `PosteriorUpdater` moves to [M08](M08-dynamics.md).
- **Category tags have no causal meaning.** They are never read by inference.
- **Only concrete operations propagate.** An op with an `AbstractTarget` end is hedged or waits; it never shocks a value (plan D10).
- **Serialization is canonical.** Every type round-trips through `canonical_json` bit for bit.

## Known issues and planned

- Units: the scale is set once and never re-estimated, so "one sd" is a designer's unit (ml-stack §1, F-C3). R3 plans per-kind transforms, realized-volatility scales with vintages, and reporting in native units.
- Existence is a Beta pseudo-count that cannot learn absence (ml-stack §4.2, S-M1). R1 replaces it with inclusion log-odds in the filter. The type stays; its meaning changes.

## Done when

- `tests/unit/model/` round-trips every type, checks id rules, and checks specificity.
- A snapshot from before the additions loads and re-hashes identically.
