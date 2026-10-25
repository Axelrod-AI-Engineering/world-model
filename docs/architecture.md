# Architecture

How the repository fits together: two members with one contract between them, one service that composes them, and the
conventions every part keeps. The design of the world model itself (its modules, data model, and processes) is in
[world_model/docs/design](../world_model/docs/design/README.md); this page is the level above.

<!-- toc -->
**Contents**

- [The two members](#the-two-members)
- [What lives where](#what-lives-where)
- [Conventions every part keeps](#conventions-every-part-keeps)
- [How a document becomes a forecast](#how-a-document-becomes-a-forecast)
<!-- /toc -->

## The two members

```
                       upload                                  read, ask, propose
  agents, analysts  ────────────┐                        ┌───────────────────────  agents, PMs
                                ▼                        ▼
                     ┌─────────────────────────────────────────────────┐
                     │  service (world_model/src/axelrod_wm/api)       │   REST /v1, MCP /mcp, the demo's API
                     │  the composition root: auth, registry, jobs     │
                     └───────────────┬─────────────────────┬───────────┘
              routes_ingest.py       │                     │       everything else
          (only ingestion + plumbing)│                     │
                                     ▼                     ▼
        ┌─────────────────────────────────┐   ┌──────────────────────────────────────┐
        │  ingestion/  axelrod_ingest     │   │  world_model/  axelrod_wm            │
        │  parse · chunk · recognize ·    │   │  the causal graph, memory, learning, │
        │  extract · lakehouse · search   │   │  inference, review, versions         │
        └──────────────┬──────────────────┘   └───────────────────┬──────────────────┘
                       │        contract/  (standard library + pydantic only)         │
                       └───────────────▶  bundle  ◀───────────────┘  world view  ◀───┘
                              ingestion writes bundles          the model writes views
                              the model reads them              ingestion reads them
```

| | `ingestion/` | `world_model/` |
|---|---|---|
| Distribution, import | `axelrod-ingest`, `axelrod_ingest` | `axelrod-world-model`, `axelrod_wm` (a name kept to avoid churning about 700 imports) |
| Does | Documents in, import bundles out; the lakehouse and its search | Holds the causal graph; learns from reviewed changes; answers what-if questions; serves the demo and the outward API |
| Depends on | Nothing of ours | `axelrod-ingest`, through the contract |
| Tested by | `ingestion/tests`, alone, 100% lines and branches of its own source | `world_model/tests`, 100% lines and branches of its own source |
| Detail | [ingestion/docs](../ingestion/docs/README.md) | [world_model/docs](../world_model/docs/README.md) |

**The contract** (`ingestion/src/axelrod_ingest/contract/`) is two things and nothing else:

- the **import bundle** (`axelrod.import/v1`): dated items, each with signals and the exact quotes that make them,
  produced by ingestion and consumed by the world model, which reviews every one;
- the **world view**: the entities, values, and links of a model as frozen records with a deterministic JSON form,
  built by the world model from its graph and read by ingestion to recognize names and read units and levels.

[contract.md](../ingestion/docs/contract.md) has both in full. Ingestion never imports the world model:
`ingestion/tests/test_boundary.py` reads the source and fails on it, and fails if the contract imports more than the
standard library and pydantic. Today the world model calls ingestion in process; because the view serializes, a
separate service can be fed over HTTP later without touching either side.

**The service** stays in `world_model/src/axelrod_wm/api` as the composition root: it owns authentication, the
registry of world models, the audit log, idempotency, and jobs (in the lakehouse's store, for now). Its ingestion
routes (documents, passages, bundles, search) are one module, `api/v1/routes_ingest.py`, which imports only
ingestion and the v1 plumbing, so they move with ingestion if it is ever served alone.

## What lives where

| Folder | Holds |
|---|---|
| `ingestion/`, `world_model/` | The members (above) |
| `docs/` | This front door |
| `configs/` | Stage settings (`world_model*.toml`): trusted issuers, owners, compartments. No secrets |
| `data/`, `feedback/`, `var/` | Local and gitignored: client content, meeting notes, runtime data |
| `scripts/` | The coverage gate and the docs tools (contents, diagrams, links) |
| `tests/` | The repository's own tests: the Railway drift verifier, the gate, the links |
| `.railway/`, `Dockerfile`, `ingestion/Dockerfile*` | The hosted deployment, three services (world model, ingestion, data): IaC, start and release scripts, the Railway CLI's `package.json` ([deployment.md](deployment.md#three-services)) |

`world_model/src/axelrod_wm/paths.py` is the one source of the roots: `REPO_ROOT` (which holds `data/`, `var/`,
`configs/`) and `WM_ROOT` (`world_model/`, which holds `examples/`, `taxonomy/`, `configs/` and `web/`). The Docker
image installs the package without the source tree and sets `AXELROD_ROOT=/app`.

## Conventions every part keeps

**Data.** Everything in the repository is synthetic: made-up companies and numbers in the tests, the examples, and the
fixtures. Client content (scenarios, worlds, documents, exports) lives only in `data/` locally and on the Railway volume
when hosted; nothing under `data/` is tracked, and no tracked file carries a client's figures, names, or quotes.

**Determinism.** The same inputs give the same outputs, byte for byte:

- ingestion: ids are content hashes, every list is sorted, extractors are versioned, embeddings are exact in tests
  and rounded in deploy, and an optional LLM step is replayed from a cache ([pipeline.md](../ingestion/docs/pipeline.md#determinism));
- the world model: named random substreams, one writer, restore by state hash, and inference that never learns;
- the contract: canonical JSON, sorted by id with sorted keys, so equal values give equal bytes.

**Review.** The world model changes only through a change a person approved. Ingestion proposes; it never commits.

**Environment.** The variable names are unchanged by the split: `WORLD_MODEL_LAKE_DIR`, `WORLD_MODEL_EMBEDDER`,
`WORLD_MODEL_LLM_PROVIDER`, `WORLD_MODEL_DATA_DIR`, `WORLD_MODEL_CLIENT_DIR`. `AXELROD_ROOT` is new, and only for an
installed copy.

## How a document becomes a forecast

1. A file is uploaded (`routes_ingest.py`) and **ingestion** parses it, chunks it, finds the model's names in it
   (through the world view), extracts signals with quotes, and stores a bundle in the lakehouse.
2. The **world model** folds each item in as a market event on its own date, turns its signals into a proposed graph
   update, and stages it for review.
3. A person approves all, some, or none of it; what they keep is committed as a new version.
4. A what-if question runs on a branch of a committed version that is never merged, and answers by name, by time, and
   by path.

The first step is [ingestion/docs/pipeline.md](../ingestion/docs/pipeline.md); the rest is the
[world model's design](../world_model/docs/design/README.md) ([architecture.md of the design](../world_model/docs/design/architecture.md) draws each process).
