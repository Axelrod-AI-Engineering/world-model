# Decisions

An index. Decisions are logged next to what they govern, one log per area; this page lists the logs and records the
decisions about the repository itself. To change a decision, add a new row and mark the old one superseded; don't edit
it.

<!-- toc -->
**Contents**

- [The logs](#the-logs)
- [The repository](#the-repository)
<!-- /toc -->

## The logs

| Area | Log | What it holds |
|---|---|---|
| The world model's architecture | [world_model/docs/design/decisions.md](../world_model/docs/design/decisions.md) | D-01 to D-25: ownership of the causal core, the modules and slots, review, determinism, memory, the unified model, access, secrets |
| The outward API | [world_model/docs/design/api.md §9](../world_model/docs/design/api.md#9-decisions) | Routes, versions, scopes, errors, idempotency, pagination |
| Business construction | [world_model/docs/design/specificity.md, Decisions](../world_model/docs/design/specificity.md#decisions) | What building each company taught, as rules |
| The math and what replaces it | [world_model/docs/ml/roadmap.md](../world_model/docs/ml/roadmap.md) | R0 to R20: each heuristic and its replacement |
| Ingestion | [ingestion/docs/pipeline.md](../ingestion/docs/pipeline.md), [contract.md](../ingestion/docs/contract.md) | Rules first and the LLM last, determinism, the bundle format, the world view |
| Deployment | [deployment.md](deployment.md) | What runs, who owns what in the shared project, how a release is verified |
| The original specification | [world_model/docs/archive/plan.md](../world_model/docs/archive/plan.md) | Historical; `# DECISION:` comments in the code point into it |

## The repository

| # | Decision | Instead of | Why | Status |
|---|---|---|---|---|
| W-01 | One uv workspace with a virtual root; members `ingestion/` and `world_model/` | One package; two repositories | Ingestion can be tested, built, and later split off alone, while one lockfile keeps the two compatible | Accepted |
| W-02 | The world model's import name stays `axelrod_wm` | Renaming it to match its distribution | About 700 imports would churn for no behavior | Accepted |
| W-03 | Ingestion never imports the world model; a test reads the source and fails on it. The CI `ingestion` job installs only `axelrod-ingest` | A convention | A boundary that is not enforced erodes | Accepted |
| W-04 | Ingestion owns the contract: the bundle schema and the world view, standard library and pydantic only | The world model owning the schema | The format is what ingestion produces; the world model is one consumer | Accepted |
| W-05 | The world view is read in process today, and has a deterministic JSON round trip | An HTTP service now | Nothing needs the network yet, and the JSON form keeps that door open | Accepted |
| W-06 | The service stays in `world_model` as the composition root; its ingestion routes are one module that imports only ingestion and the v1 plumbing | Moving the service into ingestion | The service owns authentication, the registry, and jobs, which are not ingestion's | Accepted |
| W-07 | Service state (registry, audit, idempotency, jobs) stays in the lakehouse's store for now | Splitting it out | One storage interface already serves both; revisit when ingestion is served alone | Accepted |
| W-08 | Environment variable names are unchanged | Renaming them for the new layout | A deployed service reads them | Accepted |
| W-09 | Each member is gated at 100% lines and branches from its own tests; no floor, no strict list, no pragma, no omission | A repository-wide ratchet | A member cannot lean on the other's tests, and the number means one thing | Accepted |
| W-10 | `axelrod_wm/paths.py` is the one source of the roots; tests name their inputs in `tests/where.py` | `parents[N]` in each module; paths relative to the working directory | The working directory never matters, and an installed package can find its files (`AXELROD_ROOT`) | Accepted |
| W-11 | All of `data/` is local and gitignored; our own synthetic content is tracked under `world_model/` | Client content in the repository | Client content never reaches the repository | Accepted |
