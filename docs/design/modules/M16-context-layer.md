# M16 · Context layer

| | |
|---|---|
| Layer | 5 · Interfaces |
| Status | **New** |
| Code today | Nothing. Pieces exist: `api/find.py`, forecast briefs, the ledger, and the import bundle. |
| Target | `axelrod_wm/context/`: `verbs.py`, `retrieve.py`, `mcp_server.py`, `schemas.py` |

## Purpose

How agents and analysts reach the world model. It gives a small set of verbs, over MCP and REST, that let an agent:

- recall what the model knows, at a version and with provenance;
- ask it a what-if question;
- trace where a number came from;
- propose something for it to learn, which a person reviews;
- send feedback on a forecast.

It is a layer *on* the model, not a second model. It holds no facts of its own.

The verbs follow Cognee's remember / recall / improve / forget. The provenance and time model come from Semantica. One difference matters: **no verb writes to the model without review** ([frameworks.md](../frameworks.md)).

## Owns

| Verb | Cognee analogue | Does | Reaches |
|---|---|---|---|
| `recall(query, as_of?, scope?)` | recall / search | Semantic plus graph-neighborhood retrieval over entities, values, interactions, superentities, Entity memories, and episodes, each with evidence, version, and valid time | [M15](M15-views.md) `find`, entity and memory views; slot `context_retriever` |
| `ask(question or thesis, watch?, version?)` | — (no analogue: neither framework forecasts) | Pose a thesis on a branch; return the forecast by order and path, and the brief | [M14](M14-services.md) ThesisService |
| `trace(item_id, version?)` | provenance ledger | The PROV chain of a value or interaction | [M15](M15-views.md) `provenance_view` |
| `propose(text or bundle item, quotes, confidence)` | remember / add | Submit as a market event. It is translated, refined, staged, and **waits for a person**. Returns a proposal id. | [M14](M14-services.md) UpdateService / ReviewService |
| `feedback(forecast_id, outcome or rating)` | improve | Record an outcome or a rating; scored at the horizon into track records | [M12](M12-evaluation.md) |
| `status(proposal_id)` | cognify_status | Where a proposal is: pending, approved, rejected | [M14](M14-services.md) |

There is no `forget`. Retiring an item is a structural proposal (`propose` with a retire operation) that a person reviews, and history is never deleted.

## Interface

```python
class ContextLayer:
    def recall(self, query: str, *, as_of: datetime | None = None, scope: list[str] | None = None,
               k: int = 20) -> list[Fact]
    def ask(self, question: str | Thesis, *, watch: list[str] = (), version: int | None = None) -> ForecastAnswer
    def trace(self, item_id: str, *, version: int | None = None) -> Lineage
    def propose(self, item: ImportItem | str, *, by: str, confidence: float = 1.0) -> ProposalRef
    def feedback(self, forecast_id: str, *, outcome: dict | None = None, rating: int | None = None, by: str) -> None
    def status(self, proposal_id: str) -> ProposalRef

class Fact(BaseModel):            # every recalled item carries where it came from and when it held
    item_id: str; kind: str; text: str; value: DistSummary | None
    version: int; valid_from: datetime | None; valid_to: datetime | None; recorded_at: datetime
    evidence: list[EvidenceRef]; trust_tier: str | None
```

MCP tools are the same six verbs, with JSON schemas generated from these pydantic types.

## Slots

| Slot | Default | Alternatives |
|---|---|---|
| `context_retriever` (new) | find_plus_neighborhood (today's `find`, widened by hops, ranked by significance) | embedding (structured embeddings, [M10](M10-learning-long-term.md#representations-the-plan-for-kinds)); cognee_adapter (if a Cognee research memory is attached, recall across its documents too) |

## Depends on / used by

- Depends on: [M14](M14-services.md), [M15](M15-views.md), [M12](M12-evaluation.md).
- Used by: external agents (MCP), and the web app's chat panel ([M18](M18-web.md)).

## Flow

[architecture.md §10, an agent through the context layer](../architecture.md#an-agent-through-the-context-layer).

## Invariants

- **Read freely, write by proposal.** `recall`, `ask`, `trace`, and `status` are reads. `propose` and `feedback` only ever create a proposal or an outcome record.
- **Every fact carries provenance and time.** No fact without a version, evidence, and a recorded time.
- **Auth and scope.** A login sees the engine for its scenario only (as per-login engines do today).
- **Inference never learns** applies to agents too: `ask` runs on a branch.

## Known issues and planned

- The first version wraps the existing find, theses, and ledger. Embedding recall waits on R5's structured embeddings.

## Done when

- Contract tests for each verb on the small demo.
- An MCP smoke test: an agent recalls, asks a thesis, traces a value, and proposes an article. The proposal appears in Review, pending.
