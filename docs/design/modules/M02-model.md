# M02 · Model

**Layer** 1 · **Package** `model/` · **Status** exists; `events/` and `Forecast` merge into it, and `PosteriorUpdater` moves out to M07.
**Code today:** `model/` (about 1.9k lines), `events/`, `inference/records.py`.

<!-- toc -->
**Contents**

- [Purpose](#purpose)
- [Owns](#owns)
- [Additions this design makes](#additions-this-design-makes)
- [Depends on](#depends-on)
- [Invariants](#invariants)
- [Planned](#planned)
- [Done when](#done-when)
<!-- /toc -->

## Purpose

The data model: pure pydantic types with indexes and no inference. Everything the system knows is one of these types, and everything it writes is a change to one of them. Terms follow the [glossary](../glossary.md).

## Owns

| Type | Key fields |
|---|---|
| `Entity` | id, name, kind (company, person, agency, market, macro_factor, external_factor, other), aliases, category_tags, features, subentity_ids, generalization_id, origin |
| `Subentity` | id = `<entity>.<slug>`, attribute_kind, unit, scale, anchor, link, prior, posterior, level_mean/var/noise, observed, constraint (soft economic bound), user_confidence, history |
| `Interaction` | source_id, target_id (subentities), label, edge_type, existence (Beta), forward and reverse `EdgeDynamics(effect, KernelSpec(delay, lag, duration))`, parameters (moderators: multiplicative, threshold, additive), evidence, time_states, retired_at |
| `SuperentityPattern` / `SuperentityInstance` / `SuperInteraction` | roles, relations, sub_pattern_ids, support, status, rival_ids, track_record / bindings, interaction_ids, child_instance_ids / kind (causal, shares_members) |
| `Taxonomy`, `Generalization`, `Signature` | concepts, for objects and for interactions |
| `Hypothesis` | kind, statement, interaction or decision (subentity, change, window), probability, informational_value, half_life_days (14), status (open, supported, refuted, expired) |
| `CausalGraph` | the indexes over all of the above |
| `MarketEvent` | kind, channel (scraper, data_feed, user), published_at, occurred_at, headline, body, url |
| `GraphUpdateEvent` | kind (real, hypothetical), ops, specificity (generalization 0, entity 1, subentity 2) |
| Operations | `AddEntity`, `AddSubentity`, `ObserveValue`, `ChangeValue` (intervention = do()), `AddInteraction`, `ReweightInteraction`, `AnnotateInteraction`, `ProposeHypothesis`, `ProposeSuperentity`, `DissolveSuperentity`, `RetireEntity`, `RetireInteraction` |
| `Thesis` | question, mode, event (hypothetical), horizon_days (182), targets, target_groups, posed_by, pinned |
| Records | `Evidence`, `Explanation`, `Forecast` (based_on_version, seed, config_hash, scenarios, densities, paths), `ForecastScenario` |

The data model as a diagram: [architecture.md §7](../data-model.md).

## Additions this design makes

These are additive fields with defaults, so old snapshots still load.

| Field | On | From | Why |
|---|---|---|---|
| `valid_from`, `valid_to`, `recorded_at` | TimeState, Interaction, Evidence | Semantica | "What did we believe on date X about date Y"; leak-free backtests |
| `superseded_by`, `supersession_reason` | Interaction, TimeState | Cognee | Supersede, never delete |
| `identity` | Entity | Cognee | One real actor, one id |
| `evidence_type`, `source_credibility`, `trust_tier` | Evidence | R11, Semantica | Weigh and show how a claim was obtained and corroborated |
| `vintage`, `reference_period`, `release_ts` | ObserveValue, Evidence | R15 | Point-in-time data |
| `expectation` | ObserveValue | R13 | Read releases as surprises (pricing in) |

## Depends on

[M01](M01-foundation.md).

## Invariants

- No logic beyond the types.
- **Category tags have no causal meaning.**
- **Only concrete operations propagate.** An op with an abstract end is hedged; it never shocks a value.
- Every type round-trips through `canonical_json` bit for bit.

## Planned

- Units are set once and never re-estimated (F-C3). R3 plans per-concept transforms and realized-volatility scales.
- Existence cannot learn absence (S-M1). R1 replaces it with inclusion log-odds.

## Done when

- Every type round-trips.
- A snapshot from before the additions loads and re-hashes identically.
