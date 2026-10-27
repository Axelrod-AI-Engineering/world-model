# Retrieval API

One call returns the passages from your ingested documents that best answer a query. Each passage comes with its
citation, the companies and quantities it names, and the surrounding text if you ask for it. It is built for RAG
(retrieval-augmented generation): put the passages in a model's context, and cite them.

<!-- toc -->
**Contents**

- [Quick start](#quick-start)
- [The request](#the-request)
- [The answer](#the-answer)
- [How passages are ranked](#how-passages-are-ranked)
- [Paging](#paging)
- [Errors](#errors)
- [Tips](#tips)
<!-- /toc -->

## Quick start

```bash
API=https://<host>/v1
AUTH="Authorization: Bearer <your key>"

curl -s -H "$AUTH" "$API/world-models/<world_model_id>/chunks?q=what+drove+net+interest+income&limit=5"
```

```python
import httpx

api = httpx.Client(base_url="https://<host>/v1", headers={"Authorization": "Bearer <your key>"})
page = api.get("/world-models/<world_model_id>/chunks",
               params={"q": "what drove net interest income", "source_type": ["broker_research", "filing"],
                       "published_from": "2026-07-01T00:00:00Z", "context": 1, "limit": 5}).json()
for p in page["data"]:
    c = p["citation"]
    print(f'{c["title"]} ({c["publisher"]}, {c["event_time"][:10]}): {p["text"]}')
```

A key that only reads (`world_model:read`) is enough. `GET /v1/world-models` lists the world models your key can
read. You only see your own organization's documents.

## The request

`GET /v1/world-models/{world_model_id}/chunks`

| Parameter | Default | What it does |
|---|---|---|
| `q` | required | The question or keywords, 1–500 characters |
| `mode` | `hybrid` | `hybrid` uses all three rankings (below). `keyword`, `semantic`, or `graph` uses one |
| `document_id` | | Only these documents |
| `source_type` | | Only these kinds of document: `broker_research`, `expert_call`, `news`, `central_bank`, `data`, `filing`, `client_model`, `other` |
| `source` | | Only documents from these sources (case does not matter) |
| `entity_id` | | Only documents that name one of these companies or other entities (ids from `GET …/entities`) |
| `published_from`, `published_to` | | Only documents dated in `[from, to)`. A document's date is its publication date, or the day it was uploaded when it has none. Use ISO 8601 times; a time without a zone is read as UTC |
| `context` | `0` | How many neighbouring passages to return on each side of each passage (0–3) |
| `per_document` | `0` | The most passages to return from any one document; `0` means no limit. Use 1–2 to spread results across sources |
| `limit` | `10` | Passages per page (1–100) |
| `cursor` | | The `meta.next_cursor` of the previous page |

To give several values for a filter, repeat the parameter (`source_type=news&source_type=filing`), up to 100 values
each. A document passes a filter when it matches any of the values, and it must pass every filter you give.

## The answer

```json
{
  "data": [{
    "document_id": "9f2c4e1ab0d37c55e81f0a64",
    "ordinal": 12,
    "text": "Net interest income rose 4% y/y as deposit costs stabilised.",
    "start": 5120, "end": 5181, "page": 3, "section": "Results",
    "score": 0.04918,
    "scores": {"keyword": 7.21, "semantic": 0.69, "graph": 1.0},
    "why": ["keyword", "semantic", "graph"],
    "mentions": [{"entity_id": "acme_bank", "attribute_id": "acme_bank.net_interest_income",
                  "surface": "Net interest income"}],
    "before": ["Third-quarter results beat expectations."],
    "after": ["Fee income was flat."],
    "citation": {"document_id": "9f2c4e1ab0d37c55e81f0a64", "title": "Acme Bank Q3 review",
                 "filename": "acme_q3.pdf", "publisher": "Example Securities", "source_type": "broker_research",
                 "published_at": "2026-10-05T00:00:00Z", "event_time": "2026-10-05T00:00:00Z", "url": null}
  }],
  "meta": {"request_id": "…", "limit": 10, "next_cursor": "eyJvIjoxMCwicSI6Ii4uLiJ9", "version": {"number": 1712, "…": "…"}}
}
```

- **`score`** gives the order: higher is better. It only compares passages within one answer.
- **`scores`** is each ranking's own score. `why` lists the rankings that found the passage, and adds `any word` when
  the keyword ranking matched only some of your words.
- **`mentions`** are the entities (and their quantities, as `attribute_id`) that the passage names.
- **`before`** and **`after`** hold the neighbouring passages, in document order. They are empty unless you set
  `context`.
- **`citation`** names the source document. `publisher` is empty when the document doesn't say who published it. The
  whole document is at `GET …/documents/{document_id}`, and this one passage is at
  `GET …/documents/{document_id}/chunks/{ordinal}`.

## How passages are ranked

| Ranking | Finds |
|---|---|
| `keyword` | Passages containing your words, ranked by BM25, a standard relevance score. It requires every word first, and falls back to any word if nothing contains them all. Words are stemmed, so "rates" also matches "rate" |
| `semantic` | Passages whose meaning is closest to the query, by embedding similarity, even when the wording differs |
| `graph` | Passages that name the companies and quantities your query names, most mentions first |

`hybrid` merges the three lists by reciprocal rank: a passage scores higher the nearer the top it is in each list,
and the more lists it is in. The same request over the same documents always returns the same passages in the same
order. Ties are broken by document, then by position.

## Paging

Each answer ends with `meta.next_cursor`. Pass it as `cursor`, along with the same query and filters, to get the next
page. It is `null` on the last page. A cursor only works for the query and filters that produced it; with any other
query it returns `400 invalid_cursor`. You can change `limit` and `context` between pages. Paging goes at most 1,000
passages deep; to look further, narrow the query with filters.

## Errors

Errors are RFC 9457 problem details (`application/problem+json`) with a stable `code`:

| Status | Code | When |
|---|---|---|
| 400 | `invalid_cursor` | The cursor is from another query, or was not issued by this service |
| 401 | `authentication_required`, `invalid_token` | The key is missing or wrong |
| 403 | `insufficient_scope` | The key cannot read this world model |
| 404 | `world_model_not_found` | No such world model for your organization |
| 422 | `invalid_request` | A parameter is out of range: an empty `q`, an unknown `mode`, `context` above 3, or more than 100 values for one filter. `errors` lists each one |
| 503 | `issuer_unavailable` | The service could not check a signed token just now; retry |

Every answer carries an `X-Request-Id` header. Include it when you report a problem.

## Tips

- **Ask in plain language.** `hybrid` handles questions and keywords alike. Use `keyword` when you need exact terms,
  such as a figure, a code, or a quote.
- **Filter rather than paging deep.** Filters are applied before ranking, so a narrow query costs less and ranks
  better than reading many pages.
- **Spread your sources.** `per_document=1` or `2` stops one long report from filling the page.
- **Give the model enough to read.** `context=1` returns each passage with its neighbours. That helps when a sentence
  depends on the one before it.
- **Look up ids first.** `GET …/entities?q=<name>` finds an entity's id for `entity_id`. `GET …/documents` lists the
  documents and their ids.
- **Agents** can call the same retrieval as the MCP tool `world_model_retrieve` at `/mcp`.
