# Requirements

What the system must do for its users (functional), and what it must be capable of: its hard limits and performance today, and the targets for the next horizon (nonfunctional). The user stories follow one real workflow: a portfolio manager's oil-to-portfolio canvas (Emily's demo). Her figures stay out of this repository; the demo's data is synthetic.

<!-- toc -->
**Contents**

- [Who uses it](#who-uses-it)
- [Functional requirements](#functional-requirements)
- [Nonfunctional requirements](#nonfunctional-requirements)
<!-- /toc -->

## Who uses it

| Persona | Where | Wants |
|---|---|---|
| **Portfolio manager** (external; for example, a cross-asset PM with about 50 names) | Predict | To know where a shock shows up in the book, when, by which path, and how sure the model is |
| **Analyst** (internal; Axelrod's backend users) | Learn | To keep the model current from research, and to be sure that nothing enters it unchecked |
| **Agent** (a research or assistant agent) | Context layer | To recall what the model knows, ask it questions, and propose what it should learn |
| **Engineer / operator** | Code, deployment | To change one part without breaking the others, and to restore any version |

## Functional requirements

Each story says who wants what and why; the status says how much of it exists. **Built** means in the code and the demos. **Partial** means a simpler version exists. **Planned** means designed, with its module named.

### Portfolio manager (Predict)

| # | As a PM, I want to… | So that… | Status | Where |
|---|---|---|---|---|
| FR-01 | ask "what if oil stays high for 3, 6, 12, or 18 months?" and pick a ready-made scenario or type my own | I can test my thesis without building a model | Built: Pose a thesis; Emily's ready-made scenarios | M10, M13 |
| FR-02 | see where the shock shows up in my book, and **when** | I know which names to act on first | Built: forecasts per value, entity, sector, and superentity, over the horizon | M10 |
| FR-03 | see the **transmission path** from the shock to each name (oil → rates → FX → my names), order by order | I can check the reasoning, and the second- and third-order effects analysts miss | Built: orders, paths, the transmission grid | M06, M16 |
| FR-04 | see rival scenarios (base, plausible, severe, tail) as one distribution, with their weights | I see the spread, not a single number | Built: unify mixes rivals; weights shown | M10 |
| FR-05 | drill into one name (for example, a Japanese insurer) and see which channels move it, with earnings kept apart from the balance sheet | I can talk about the name, not the model | Partial: a name's values and drivers; separating earnings from balance sheet needs those subentities | M02, M14 |
| FR-06 | see, for every number, whether it is a **fact**, an **assumption**, or **our view**, and where it came from | I can trust it and defend it | Partial: evidence and the commit log; labels and `trace` planned | M02 (evidence types), M15 |
| FR-07 | change an assumption (an exposure, an effect) and **re-run** the forecast | I can stress my own view | Partial: edit and re-run a thesis; overriding an interaction in a thesis is planned | M10, M13 |
| FR-08 | read a short **brief**, with a timeline table and the paths, and **annotate** it | I can share the answer with my team | Partial: briefs built; timeline table and annotations in progress | M14, M16 |
| FR-09 | have every name I track covered, or be told it is not reached | no tracked name drops out silently | Built: the context network | M10 |
| FR-10 | see the past episodes the forecast leans on (earlier oil shocks) | I can judge the analogy | Partial: recall by signature; structural analogy planned | M06, cognition F8 |
| FR-11 | record a decision on a forecast and see it scored when the horizon passes | the model earns trust, or loses it | Built: decisions, CRPS, track records | M11 |

### Analyst (Learn)

| # | As an analyst, I want to… | So that… | Status | Where |
|---|---|---|---|---|
| FR-12 | import a bundle of research and review each item on its date | the model catches up with what I have read | Built: `axelrod.import/v1` | M05, M13 |
| FR-13 | see everything an event would change, down to the third-order ripple, before it is committed | nothing enters the model unchecked | Built: staged review | M13 |
| FR-14 | approve some changes and not others, and say how confident I am | my judgment shapes what is learned | Built: selection, confidence, ripple weights | M13 |
| FR-15 | add what I know with no article | expert knowledge counts | Built: Add from your own knowledge | M13 |
| FR-16 | leave a vague mention unresolved until evidence settles it | the model is not falsely precise | Built: hedges | M05 |
| FR-17 | group, dissolve, and retire structure | the model's structure stays sensible | Built | M09, M13 |
| FR-18 | see the history, compare versions, and open an old one | I can audit and explain any change | Built: log, show, diff, the scrubber | M04, M14 |

### Agent and operator

| # | As… I want to… | So that… | Status | Where |
|---|---|---|---|---|
| FR-19 | an agent: recall facts with their provenance, ask a thesis, trace a number, and propose an article | agents use the model without bypassing review | Planned | M15 |
| FR-20 | an operator: run one engine per login, each with its own demo, and switch demos | clients see their own model | Built (per login); switching in progress | M14, M17 |
| FR-21 | an operator: restore any version from the ledger and check its hash | an incident never loses the model | Built | M04 |

## Nonfunctional requirements

### Measured today

Measured on a laptop (Apple silicon), from the demos' own data, on 2026-10-14.

| Quantity | Small demo | Production demo | Emily's demo |
|---|---|---|---|
| Entities · subentities · interactions | 8 · 17 · 20 (after 24 examples) | 53 · 159 · 165, with 24 superentity instances | 19 · 37 · 42, with 6 superentity instances |
| Start (cached) | 0.1 s | 4.8 s | 0.1 s |
| Stage a review (whole learning on a copy) | 0.03 s | 2.3 s median, 2.7 s worst (an oil shock rippling to about 20 values) | — |
| Pose a thesis (forecast + brief) | 1.5 s | 6.9 s median, 9.9 s worst (4 theses) | 2.3 s median, 2.8 s worst (4 theses) |
| State size (one snapshot) | 0.1 MB | 11.3 MB | under 0.1 MB |
| First start, no cache | seconds | about 2.5 min (three years of history) | seconds (no history) |
| History storage | — | 456 MB ledger + 235 MB snapshots for three years | — |
| Peak memory (process) | — | about 3.5 GB | — |

### Hard limits (by design or by configuration)

| Limit | Value | Where set |
|---|---|---|
| Monte Carlo samples per run | 400 | `propagation.samples` |
| Forecast horizon | 182 days by default | `Thesis.horizon_days` |
| Order of transmission read out | up to 6 | `shared/transmission.py` |
| Scenarios kept per thesis | 8 | `unify.max_scenarios` |
| Candidates per hedged end | 4, plus an open share | `refinement` |
| Time states kept per value | 260 | `Subentity.history` |
| Update runs at once | 1 per engine; one engine per login | `UpdateCycle`, `api/app.py` |
| Replicas | 1 (shared session per login) | `.railway/railway.ts` |
| Health check start window | 600 s (the first start replays history) | `.railway/railway.ts` |

### Qualities

| Quality | Requirement | Today |
|---|---|---|
| **Determinism** | The same version, config, and seed give the same forecast, bit for bit | Built: named random substreams; restore is hash-checked |
| **Auditability** | Every change names its process, proposal, and who vetted it; any version can be restored | Built: the ledger |
| **Vetted learning** | Nothing that needs review is learned before a person approves it | Built |
| **Isolation of asking** | A thesis never changes memory | Built: branches |
| **Availability** | Restarts on failure; state survives a restart | Partial: the model survives; pending proposals and forecasts do not yet (T-12) |
| **Security** | Every page and API call needs a signed-in session; no client data in the repository | Built: HMAC session cookies; client data gitignored |
| **Data** | Synthetic in every demo; real names only to make the graph concrete | Built |

### Next horizon (targets, not commitments)

| Target | From | To | Needs |
|---|---|---|---|
| Graph size | about 50 entities | 500–2,000 entities (a book of 50 names and their drivers) | A columnar store; sparse propagation; JAX |
| Thesis latency | 7–10 s on 53 entities | under 5 s at p95 on the larger graph | Vectorized propagation; caching networks by version |
| Staging latency | 2–3 s on 53 entities | under 2 s at p95 | Copy-on-write branches (T-10) |
| Storage | JSONL + gzip snapshots | Append-only columnar tables, compacted | M04 |
| Users | one session per login | many users per client, with roles | Accounts and permissions |
| Data | synthetic and imported research | vintage-aware data feeds, read point in time | R15 |
| Agents | none | MCP clients, by proposal only | M15 |
